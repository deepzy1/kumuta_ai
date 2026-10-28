"""Contract tests use a temporary legacy database and an isolated fake Google boundary."""
import asyncio
import base64
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pymupdf as fitz
import httpx
from cryptography.fernet import Fernet
from pwdlib import PasswordHash
from sqlalchemy import func, select

TEMP = tempfile.TemporaryDirectory()
DB_PATH = Path(TEMP.name) / 'legacy.db'
os.environ['DATABASE_URL'] = f'sqlite:///{DB_PATH}'
os.environ['DOCUMENT_STORAGE_DIR'] = str(Path(TEMP.name) / 'documents')
os.environ['JWT_SECRET'] = 'test-only-secret-' * 4
os.environ['API_KEY_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
os.environ['GEMINI_API_KEY'] = 'shared-key-must-never-be-used'
with sqlite3.connect(DB_PATH) as db:
    db.executescript('''
    CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(320) UNIQUE NOT NULL, password_hash VARCHAR(512) NOT NULL);
    CREATE TABLE conversations (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), title VARCHAR(120) NOT NULL);
    CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id), role VARCHAR(16) NOT NULL, content TEXT NOT NULL, attachment_name VARCHAR(255), attachment_mime VARCHAR(100), attachment_data TEXT);
    INSERT INTO conversations VALUES (1, 1, 'Existing chat');
    INSERT INTO messages VALUES (1, 1, 'user', 'Keep this original message', NULL, NULL, NULL);
    ''')
    db.execute('INSERT INTO users VALUES (1, ?, ?)', ('existing@example.com', PasswordHash.recommended().hash('password123')))

from app import gemini, main
from app.database import Conversation, Message, SessionLocal, Summary, Usage, User, migrate
from google.genai import types


class ProviderError(Exception):
    def __init__(self, code):
        self.code = code


class AsyncRows:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        return self.iterate()

    async def iterate(self):
        for row in self.rows:
            yield row


class FakeClient:
    calls = []
    count_fail = False
    count_entered = None
    count_release = None

    def __init__(self, key):
        self.key = key
        self.aio = self
        self.models = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def list(self):
        if 'invalid' in self.key:
            raise ProviderError(403)
        return AsyncRows([
            types.Model(name='models/gemini-test-flash', display_name='Test Flash', description='Multimodal chat', supported_actions=['generateContent', 'countTokens'], input_token_limit=100000, output_token_limit=8192),
            types.Model(name='models/gemini-test-pro', display_name='Test Pro', supported_actions=['generateContent'], input_token_limit=200000),
            types.Model(name='models/gemini-test-image', supported_actions=['generateContent']),
            types.Model(name='models/gemini-embedding', supported_actions=['embedContent']),
            types.Model(name='models/gemini-test-tts', supported_actions=['generateContent']),
        ])

    async def count_tokens(self, **kwargs):
        self.calls.append(('count', self.key, kwargs))
        if self.count_entered:
            self.count_entered.set()
            await self.count_release.wait()
        if self.count_fail:
            raise ProviderError(500)
        payload = kwargs['config'].http_options.extra_body['generateContentRequest']
        self_system = payload['systemInstruction']['parts'][0]['text']
        assert kwargs['config'].system_instruction is None, 'Developer API does not support this SDK config field'
        return SimpleNamespace(total_tokens=gemini.estimate([types.Content.model_validate(content) for content in payload['contents']], self_system))

    async def generate_content_stream(self, **kwargs):
        self.calls.append(('stream', self.key, kwargs))
        if any('quota-trigger' in (part.text or '') for content in kwargs['contents'] for part in content.parts):
            raise ProviderError(429)
        async def chunks():
            yield SimpleNamespace(text='Hello ', usage_metadata=None)
            await asyncio.sleep(0)
            yield SimpleNamespace(text='世界!\n```python\nprint(1)\n```', usage_metadata=SimpleNamespace(prompt_token_count=123, candidates_token_count=20, total_token_count=150))
        return chunks()

    async def generate_content(self, **kwargs):
        self.calls.append(('summary', self.key, kwargs))
        return SimpleNamespace(text='Compact summary: retain original facts and attachment findings.',
            usage_metadata=SimpleNamespace(prompt_token_count=123, candidates_token_count=20, total_token_count=150))


def events(response):
    return [(frame.split('\n')[0].removeprefix('event: '), json.loads(frame.split('\ndata: ')[1]))
            for frame in response.text.strip().split('\n\n')]


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeClient.calls.clear()
        FakeClient.count_fail = False
        FakeClient.count_entered = FakeClient.count_release = None
        gemini._models_cache.clear()
        gemini._context_cache.clear()
        self.patcher = patch.object(gemini, 'client_for', side_effect=FakeClient)
        self.patcher.start()
        self.pricing_patcher = patch.object(gemini.pricing, 'catalog', new=AsyncMock(return_value={
            'checked_at': main.now(), 'models': {'gemini-test-flash': 'free', 'gemini-test-pro': 'free'}}))
        self.pricing_patcher.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test')
        email = f'{__import__("uuid").uuid4().hex}@example.com'
        result = await self.client.post('/auth/signup', json={'email': email, 'password': 'password123'})
        self.assertEqual(result.status_code, 200, result.text)
        self.token = result.json()['token']
        self.headers = {'Authorization': f'Bearer {self.token}'}
        self.key = 'AQ.test-key-for-this-user'

    async def asyncTearDown(self):
        await self.client.aclose()
        self.patcher.stop()
        self.pricing_patcher.stop()

    async def call(self, method, path, **kwargs):
        return await self.client.request(method, path, headers=self.headers, **kwargs)

    async def connect(self):
        response = await self.call('PUT', '/settings/api-key', json={'api_key': self.key})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    async def conversation(self):
        result = await self.call('POST', '/conversations')
        return result.json()['id']

    async def send(self, cid, text='Explain this', **kwargs):
        return await self.call('POST', f'/conversations/{cid}/messages', data={'text': text}, **kwargs)

    async def test_legacy_migration_preserves_data_and_is_repeatable(self):
        migrate()
        with SessionLocal() as db:
            self.assertEqual(db.get(Message, 1).content, 'Keep this original message')
            self.assertEqual(db.get(Conversation, 1).title, 'Existing chat')
        self.assertTrue(list(Path(TEMP.name).glob('legacy.db.pre-kumuta-*.bak')))
        login = await self.client.post('/auth/login', json={'email': 'existing@example.com', 'password': 'password123'})
        self.assertEqual(login.status_code, 200)
        response = await self.client.get('/conversations/1', headers={'Authorization': 'Bearer ' + login.json()['token']})
        self.assertEqual(response.json()['messages'][0]['content'], 'Keep this original message')

    async def test_key_encryption_validation_replacement_and_deletion(self):
        response = await self.connect()
        self.assertNotIn(self.key, response.text)
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == response.json()['email']))
            self.assertNotEqual(user.encrypted_api_key, self.key)
            self.assertEqual(gemini.user_key(user), self.key)
        invalid = await self.call('PUT', '/settings/api-key', json={'api_key': 'AQ.invalid-secret'})
        self.assertEqual(invalid.status_code, 400)
        self.assertNotIn('AQ.invalid-secret', invalid.text)
        malformed = await self.call('PUT', '/settings/api-key', json={'api_key': 'secret with whitespace'})
        self.assertEqual(malformed.status_code, 422)
        self.assertNotIn('secret with whitespace', malformed.text)
        self.key = 'AIza.test-replacement'
        await self.connect()
        model = await self.call('GET', '/models')
        self.assertEqual(len(model.json()['models']), 2)
        await self.call('DELETE', '/settings/api-key')
        self.assertFalse((await self.call('GET', '/auth/me')).json()['has_api_key'])
        self.assertEqual((await self.send(await self.conversation())).status_code, 428)

    async def test_stream_context_and_user_key_isolation(self):
        await self.connect()
        cid = await self.conversation()
        for _ in range(2):
            response = await self.send(cid)
            self.assertEqual(response.status_code, 200, response.text)
            frames = events(response)
            self.assertEqual([event for event, _ in frames], ['start', 'delta', 'context', 'delta', 'done'])
            self.assertIn('世界', frames[-1][1]['message']['content'])
            self.assertEqual(frames[-1][1]['message']['model'], 'gemini-test-flash')
        self.assertTrue(all(key == self.key for _, key, _ in FakeClient.calls))
        contents = [call[2]['contents'] for call in FakeClient.calls if call[0] == 'stream'][-1]
        self.assertEqual(len(contents), 3)
        usage = (await self.call('GET', '/usage')).json()
        self.assertEqual(usage['totals']['requests'], 2)
        self.assertEqual(usage['totals']['input_tokens'], 246)
        self.assertEqual(usage['totals']['total_tokens'], 300)
        context = (await self.call('GET', f'/conversations/{cid}/context')).json()
        self.assertFalse(context['estimated'])
        self.assertNotEqual(context['used_tokens'], usage['totals']['total_tokens'])
        self.assertIsNone(usage['official_quota'])

    async def test_ownership_on_every_conversation_operation(self):
        await self.connect()
        for method, path, kwargs in [
            ('GET', '/conversations/1', {}), ('PATCH', '/conversations/1', {'json': {'title': 'Steal'}}),
            ('DELETE', '/conversations/1', {}), ('GET', '/conversations/1/attachments/1', {}),
            ('GET', '/conversations/1/context', {}), ('POST', '/conversations/1/summarize', {}),
            ('POST', '/conversations/1/regenerate', {}), ('POST', '/conversations/1/messages', {'data': {'text': 'Steal'}}),
        ]:
            response = await self.call(method, path, **kwargs)
            self.assertEqual(response.status_code, 404, path)
        own = await self.conversation()
        listing = (await self.call('GET', '/conversations')).json()['items']
        self.assertEqual([item['id'] for item in listing], [own])
        self.assertEqual((await self.client.get('/usage')).status_code, 401)

    async def test_attachments_roundtrip_context_and_rejections(self):
        await self.connect()
        cid = await self.conversation()
        pdf = fitz.open(); pdf.new_page().insert_text((72, 72), 'Document facts'); raw = pdf.tobytes(); pdf.close()
        response = await self.send(cid, 'Analyze PDF', files={'attachment': ('../../document.pdf', raw, 'application/pdf')})
        self.assertEqual(response.status_code, 200, response.text)
        start = events(response)[0][1]
        self.assertEqual(start['message']['attachments'][0]['attachment_name'], 'document.pdf')
        self.assertNotIn('attachment_data', response.text)
        mid = start['message']['id']
        download = await self.call('GET', f'/conversations/{cid}/attachments/{mid}')
        self.assertEqual(download.content, raw)
        await self.send(cid, 'What was in that PDF?')
        sent = [c[2]['contents'] for c in FakeClient.calls if c[0] == 'stream'][-1]
        self.assertEqual(sent[0].parts[1].inline_data.data, raw)
        for filename, content, mime, status in [('fake.png', b'fake', 'image/png', 415),
            ('fake.pdf', b'%PDF-broken', 'application/pdf', 415), ('file.txt', b'text', 'text/plain', 415),
            ('big.png', b'x' * (main.MAX_FILE + 1), 'image/png', 413)]:
            result = await self.send(cid, files={'attachment': (filename, content, mime)})
            self.assertEqual(result.status_code, status, result.text)
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), 0)
        image = pixmap.tobytes('png')
        result = await self.send(cid, 'Image', files={'attachment': ('test.png', image, 'image/png')})
        self.assertEqual(result.status_code, 200, result.text)

    async def test_multiple_attachments_roundtrip_limits_and_ownership(self):
        await self.connect()
        cid = await self.conversation()
        pdf = fitz.open(); pdf.new_page(); raw = pdf.tobytes(); pdf.close()
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), 0).tobytes('png')
        files = [('attachments', ('screenshot.png', image, 'image/png')),
                 ('attachments', ('facts.pdf', raw, 'application/pdf'))]
        response = await self.send(cid, 'Text alongside both files', files=files)
        self.assertEqual(response.status_code, 200, response.text)
        message = events(response)[0][1]['message']
        self.assertEqual(len(message['attachments']), 2)
        self.assertEqual(message['content'], 'Text alongside both files')
        for attachment, expected in zip(message['attachments'], [image, raw]):
            route = f"/conversations/{cid}/attachments/{message['id']}/{attachment['id']}"
            self.assertEqual((await self.call('GET', route)).content, expected)
            self.assertEqual((await self.client.get(route)).status_code, 401)
            self.assertEqual((await self.call('GET', f"/conversations/1/attachments/{message['id']}/{attachment['id']}")).status_code, 404)
        sent = [c[2]['contents'] for c in FakeClient.calls if c[0] == 'stream'][-1]
        self.assertEqual([p.inline_data.data for p in sent[0].parts if p.inline_data], [image, raw])
        await self.send(cid, 'Remember both files')
        sent = [c[2]['contents'] for c in FakeClient.calls if c[0] == 'stream'][-1]
        self.assertEqual(len(sent[0].parts), 3)
        before = (await self.call('GET', f'/conversations/{cid}')).json()['messages']
        result = await self.send(cid, files=files * 3)
        self.assertEqual(result.status_code, 413)
        mixed = await self.send(cid, files=files + [('attachments', ('invalid.txt', b'no', 'text/plain'))])
        self.assertEqual(mixed.status_code, 415)
        # Exercise aggregate size independently of individual file limits.
        from app import attachments as attachment_service
        with patch.object(attachment_service, 'MAX_TOTAL_FILES', 10):
            self.assertEqual((await self.send(cid, files=files)).status_code, 413)
        self.assertEqual((await self.call('GET', f'/conversations/{cid}')).json()['messages'], before)
        # Original single-file rows still download and enter Gemini history.
        with SessionLocal() as db:
            legacy = Message(conversation_id=cid, role='user', content='Legacy PDF', attachment_name='old.pdf',
                attachment_mime='application/pdf', attachment_size=len(raw), attachment_data=base64.b64encode(raw).decode())
            db.add(legacy); db.commit(); mid = legacy.id
        self.assertEqual((await self.call('GET', f'/conversations/{cid}/attachments/{mid}')).content, raw)
        await self.send(cid, 'Read legacy PDF too')
        await self.call('DELETE', f'/conversations/{cid}')
        from app.database import Attachment
        with SessionLocal() as db:
            self.assertIsNone(db.get(Attachment, message['attachments'][0]['id']))

    async def test_tiers_free_default_paid_opt_in_and_unknown_models(self):
        self.pricing_patcher.new.return_value['models']['gemini-test-flash'] = 'paid'
        await self.connect()
        account = (await self.call('GET', '/auth/me')).json()
        self.assertEqual(account['preferred_model'], 'gemini-test-pro')
        self.assertFalse(account['allow_paid_models'])
        self.assertEqual((await self.call('PATCH', '/settings/model', json={'model': 'gemini-test-flash'})).status_code, 400)

        await self.call('PATCH', '/settings/model-access', json={'allow_paid_models': True})
        selected = await self.call('PATCH', '/settings/model', json={'model': 'gemini-test-flash'})
        self.assertEqual(selected.json()['preferred_model'], 'gemini-test-flash')
        self.assertEqual((await self.send(await self.conversation())).status_code, 200)
        reset = await self.call('PATCH', '/settings/model-access', json={'allow_paid_models': False})
        self.assertEqual(reset.json()['preferred_model'], 'gemini-test-pro')
        self.pricing_patcher.new.return_value['models'].pop('gemini-test-flash')
        available = (await self.call('GET', '/models?refresh=true')).json()['models']
        self.assertEqual(available[0]['tier'], 'free')
        self.assertEqual(available[1]['tier'], 'unknown')
        self.assertEqual((await self.call('PATCH', '/settings/model', json={'model': 'gemini-test-flash'})).status_code, 400)


    async def test_expired_cached_pricing_requires_refresh_without_storing_message(self):
        await self.connect()
        cid = await self.conversation()
        cached = gemini._models_cache[next(iter(gemini._models_cache))][1]
        for model in cached:
            model['pricing_checked_at'] = '2020-01-01T00:00:00+00:00'
        response = await self.send(cid)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Refresh models', response.text)
        self.assertEqual((await self.call('GET', f'/conversations/{cid}')).json()['messages'], [])
        await self.call('GET', '/models?refresh=true')
        self.assertEqual((await self.send(cid)).status_code, 200)

    async def test_summary_regeneration_and_history_preservation(self):
        await self.connect()
        cid = await self.conversation()
        await self.send(cid, 'Important facts')
        original = (await self.call('GET', f'/conversations/{cid}')).json()['messages']
        compact = await self.call('POST', f'/conversations/{cid}/summarize')
        self.assertEqual(compact.status_code, 200, compact.text)
        self.assertEqual((await self.call('GET', f'/conversations/{cid}')).json()['messages'], original)
        regenerated = await self.call('POST', f'/conversations/{cid}/regenerate')
        self.assertEqual(regenerated.status_code, 200, regenerated.text)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count(Message.id)).where(Message.conversation_id == cid)), 3)
            self.assertEqual(db.scalar(select(Summary).where(Summary.conversation_id == cid)).active, 0)
        self.assertIsNone((await self.call('GET', f'/conversations/{cid}')).json()['summary'])
        await self.call('POST', f'/conversations/{cid}/summarize')
        await self.send(cid, 'Continue with those facts')
        sent = [c[2]['contents'] for c in FakeClient.calls if c[0] == 'stream'][-1]
        self.assertIn('Earlier conversation summary', sent[0].parts[0].text)
        self.assertEqual(len(sent), 2)

    async def test_quota_errors_estimated_counts_and_retry(self):
        await self.connect()
        cid = await self.conversation()
        FakeClient.count_fail = True
        result = await self.send(cid, 'quota-trigger')
        frames = events(result)
        self.assertTrue(frames[0][1]['context']['estimated'])
        self.assertEqual(frames[-2][0], 'error')
        self.assertIn('quota', frames[-2][1]['message'])
        usage = (await self.call('GET', '/usage')).json()
        self.assertTrue(usage['quota_exceeded'])
        self.assertEqual(usage['totals']['estimated_requests'], 1)
        stored = (await self.call('GET', f'/conversations/{cid}')).json()['messages']
        self.assertEqual(len(stored), 1)
        with SessionLocal() as db:
            self.assertIsNone(db.get(Conversation, cid).generation_id)

    async def test_database_lease_blocks_duplicate_generation(self):
        await self.connect()
        cid = await self.conversation()
        system = gemini.SYSTEM + main.memory.GUARD + main.shared_ai.chat_instructions()
        # Fit the shared contract while remaining above the preflight-count
        # threshold, so this test still exercises concurrent lease acquisition.
        gemini._models_cache[next(iter(gemini._models_cache))][1][0]['input_token_limit'] = max(1000, gemini.estimate([], system) * 2)
        FakeClient.count_entered, FakeClient.count_release = asyncio.Event(), asyncio.Event()
        first = asyncio.create_task(self.send(cid, 'First request'))
        await asyncio.wait_for(FakeClient.count_entered.wait(), timeout=2)
        second = await self.send(cid, 'Duplicate request')
        self.assertEqual(second.status_code, 409, second.text)
        FakeClient.count_release.set()
        self.assertEqual((await first).status_code, 200)

    async def test_model_preference_search_pagination_and_delete(self):
        await self.connect()
        self.assertEqual((await self.call('PATCH', '/settings/model', json={'model': 'unknown'})).status_code, 400)
        changed = await self.call('PATCH', '/settings/model', json={'model': 'gemini-test-pro'})
        self.assertEqual(changed.json()['preferred_model'], 'gemini-test-pro')
        cid = await self.conversation()
        await self.send(cid, 'A searchable title')
        await self.send(cid, 'Second question')
        page = (await self.call('GET', f'/conversations/{cid}?limit=2')).json()
        self.assertTrue(page['has_more'])
        self.assertEqual(len(page['messages']), 2)
        earlier = (await self.call('GET', f'/conversations/{cid}?limit=2&before={page["messages"][0]["id"]}')).json()
        self.assertEqual(len(earlier['messages']), 2)
        self.assertFalse(earlier['has_more'])
        await self.call('PATCH', f'/conversations/{cid}', json={'title': 'Renamed searchable'})
        self.assertEqual(len((await self.call('GET', '/conversations?q=searchable')).json()['items']), 1)
        self.assertEqual((await self.call('PATCH', f'/conversations/{cid}', json={'title': '  '})).status_code, 422)
        await self.call('DELETE', f'/conversations/{cid}')
        self.assertEqual((await self.call('GET', f'/conversations/{cid}')).status_code, 404)
        self.assertEqual((await self.call('GET', '/usage')).json()['totals']['requests'], 2)

    async def test_two_users_generate_with_different_keys(self):
        await self.connect()
        first_cid = await self.conversation()
        await self.send(first_cid)
        second = await self.client.post('/auth/signup', json={'email': f'{__import__("uuid").uuid4().hex}@example.com', 'password': 'password123'})
        self.headers = {'Authorization': 'Bearer ' + second.json()['token']}
        self.key = 'AIza.independent-second-user'
        await self.connect()
        await self.send(await self.conversation())
        keys = [call[1] for call in FakeClient.calls if call[0] == 'stream']
        self.assertEqual(keys, ['AQ.test-key-for-this-user', 'AIza.independent-second-user'])
        self.assertEqual((await self.call('GET', f'/conversations/{first_cid}')).status_code, 404)
        self.assertEqual((await self.call('GET', '/usage')).json()['totals']['requests'], 1)

    async def test_real_sdk_serializes_context_system_and_attachment(self):
        from google import genai
        sent = []
        def handler(request):
            sent.append(request)
            return httpx.Response(200, json={'totalTokens': 321})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with genai.Client(api_key='AQ.sdk-transport-test', http_options=types.HttpOptions(httpx_async_client=http)).aio as sdk:
                contents = [types.Content(role='user', parts=[types.Part.from_text(text='Analyze this'),
                    types.Part.from_bytes(data=b'image-bytes', mime_type='image/png')])]
                result = await gemini.count_context(sdk, {'id': 'gemini-test-flash'}, contents)
        self.assertEqual(result, {'used_tokens': 321, 'estimated': False})
        payload = json.loads(sent[0].content)
        self.assertNotIn('contents', payload)
        body = payload['generateContentRequest']
        self.assertEqual(body['model'], 'models/gemini-test-flash')
        self.assertEqual(body['systemInstruction']['parts'][0]['text'], gemini.SYSTEM)
        self.assertEqual(body['contents'][0]['parts'][1]['inlineData']['data'], base64.b64encode(b'image-bytes').decode())
        self.assertEqual(sent[0].headers['x-goog-api-key'], 'AQ.sdk-transport-test')
        self.assertNotIn('AQ.sdk-transport-test', str(sent[0].url))

    async def test_context_overflow_does_not_store_rejected_message(self):
        await self.connect()
        cid = await self.conversation()
        model = gemini._models_cache[next(iter(gemini._models_cache))][1][0]
        model['input_token_limit'] = 10
        result = await self.send(cid, 'This cannot fit in the selected model context')
        self.assertEqual(result.status_code, 413)
        self.assertEqual((await self.call('GET', f'/conversations/{cid}')).json()['messages'], [])
        with SessionLocal() as db:
            self.assertIsNone(db.get(Conversation, cid).generation_id)

    async def test_normal_reply_skips_counting_and_stale_model_refresh(self):
        await self.connect()
        cache_key = next(iter(gemini._models_cache))
        gemini._models_cache[cache_key] = (0, gemini._models_cache[cache_key][1])
        with patch.object(gemini, 'discover', side_effect=AssertionError('Model refresh blocked a reply')):
            response = await self.send(await self.conversation(), 'Hi')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(any(call[0] == 'count' for call in FakeClient.calls))
        frames = events(response)
        self.assertTrue(frames[0][1]['context']['estimated'])
        actual = next(data for event, data in frames if event == 'context')
        self.assertFalse(actual['estimated'])
        self.assertEqual(actual['used_tokens'], 123)

    async def test_slow_counting_has_a_deadline_and_estimated_fallback(self):
        FakeClient.count_entered, FakeClient.count_release = asyncio.Event(), asyncio.Event()
        contents = [types.Content(role='user', parts=[types.Part.from_text(text='hello')])]
        result = await asyncio.wait_for(gemini.count_context(FakeClient(self.key),
            {'id': 'gemini-test-flash'}, contents, timeout=.02), timeout=.5)
        self.assertTrue(result['estimated'])
        self.assertGreater(result['used_tokens'], 0)

    async def test_model_specific_fast_thinking_preserves_output_limit(self):
        config = gemini.generation_config({'id': 'gemini-3.8-flash', 'output_token_limit': 65536})
        self.assertEqual(config.thinking_config.thinking_level.value, 'LOW')
        self.assertEqual(config.max_output_tokens, 8192)
        self.assertEqual(gemini.generation_config({'id': 'gemini-2.5-flash'}).thinking_config.thinking_budget, 0)
        self.assertEqual(gemini.generation_config({'id': 'gemini-2.5-pro'}).thinking_config.thinking_budget, 128)
        self.assertIsNone(gemini.generation_config({'id': 'gemini-unknown'}).thinking_config)
        self.assertEqual(gemini.provider_error(ProviderError(503)).status_code, 503)
        self.assertIn('busy', gemini.provider_error(ProviderError(503)).detail)

    async def test_disconnect_saves_partial_and_releases_lease(self):
        await self.connect()
        cid = await self.conversation()
        class DisconnectedRequest:
            calls = 0
            cookies = {}
            headers = {'authorization':'Bearer '+self.token}
            async def is_disconnected(self):
                self.calls += 1
                return self.calls > 1
        with SessionLocal() as db:
            user = main.user_from_token(DisconnectedRequest(), SimpleNamespace(credentials=self.token), db)
            response = await main.generate_reply(cid, DisconnectedRequest(), user, db, 'Stop after first chunk')
        frames = [frame async for frame in response.body_iterator]
        self.assertIn('event: done', frames[-1])
        stored = (await self.call('GET', f'/conversations/{cid}')).json()['messages']
        self.assertEqual(stored[-1]['content'], 'Hello ')
        self.assertEqual(stored[-1]['status'], 'stopped')
        with SessionLocal() as db:
            self.assertIsNone(db.get(Conversation, cid).generation_id)


if __name__ == '__main__':
    unittest.main()
