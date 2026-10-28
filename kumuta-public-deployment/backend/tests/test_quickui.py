"""QuickUI/search contracts use only the disposable legacy database and fake provider."""
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from sqlalchemy import select
import test_api as fixture
from app import gemini, quickui
from app.database import Message, QuickUIResponse, SessionLocal, User, migrate
from app.grounding import Grounding
from google.genai import types

SPEC = {'version': 1, 'title': 'A useful comparison', 'blocks': [
    {'type': 'cards', 'items': [{'label': 'Speed', 'value': 'Fast'}]},
    {'type': 'table', 'columns': ['Option', 'Value'], 'rows': [['A', 3], ['B', 4]]},
    {'type': 'chart', 'kind': 'line', 'labels': ['A', 'B'], 'series': [{'name': 'Sample', 'values': [3, 4]}]},
    {'type': 'calculator', 'operation': 'sum', 'inputs': [{'label': 'Value', 'value': 5, 'min': 0, 'max': 10, 'step': 1}]},
    {'type': 'diagram', 'syntax': 'sequence', 'text': 'Client -> Server: request\nServer --> Client: response'},
    {'type': 'checklist', 'items': [{'text': 'Review'}]},
]}
ANSWER = 'Here is a comparison.\n\n```quickui\n' + json.dumps(SPEC) + '\n```'

class SchemaTests(unittest.TestCase):
    def test_valid_content_has_readable_fallback(self):
        text, spec, error = quickui.extract(ANSWER)
        self.assertIsNone(error)
        self.assertEqual(spec['version'], 1)
        self.assertIn('| Option | Value |', text)
        self.assertNotIn('```quickui', text)
        self.assertIn('Speed', text)

    def test_invalid_and_executable_specs_fall_back_without_throwing(self):
        for block in [
            {'type': 'html', 'text': '<script>alert(1)</script>'},
            {'type': 'diagram', 'syntax': 'mermaid', 'text': '%%{init: {}}%%\ngraph LR'},
            {'type': 'diagram', 'syntax': 'mermaid', 'text': 'graph LR\nclick A "javascript:alert(1)"'},
            {'type': 'table', 'columns': ['A'], 'rows': [['a', 'b']]},
            {'type': 'chart', 'labels': ['A'], 'series': [{'name': 'A', 'values': [float('inf')]}]},
            {'type': 'calculator', 'operation': 'eval', 'inputs': []},
            {'type': 'markdown', 'text': 'Hello', 'style': 'color:red'},
        ]:
            answer = 'Readable explanation\n```quickui\n' + json.dumps({'version':1,'blocks':[block]}) + '\n```'
            text, spec, error = quickui.extract(answer)
            self.assertIsNone(spec, block)
            self.assertIn('Readable explanation', text)
            self.assertTrue(error)

    def test_grounding_filters_urls_and_places_utf8_citations(self):
        tracker = Grounding(True)
        metadata = types.GroundingMetadata(grounding_chunks=[types.GroundingChunk(web=types.GroundingChunkWeb(uri='https://example.com/fact',title='Source')),types.GroundingChunk(web=types.GroundingChunkWeb(uri='javascript:alert(1)',title='Unsafe'))],
            web_search_queries=['fact','fact'], grounding_supports=[types.GroundingSupport(segment=types.Segment(start_index=0,end_index=len('世界 fact'.encode())),grounding_chunk_indices=[0,1])])
        tracker.add(NS(candidates=[NS(grounding_metadata=metadata)]))
        tracker.add(NS(candidates=[NS(grounding_metadata=metadata)]))
        self.assertEqual(len(tracker.view()['sources']),1)
        self.assertEqual(tracker.view()['query_count'],1)
        self.assertIn('世界 fact [1](https://example.com/fact)',tracker.cite_markdown('世界 fact'))
        self.assertNotIn('[1]',tracker.cite_markdown('```quickui\n世界 fact\n```'))
        self.assertIsNone(Grounding(True).view()['query_count'])

class QuickUIAPITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.APITests.asyncSetUp
    asyncTearDown = fixture.APITests.asyncTearDown
    call = fixture.APITests.call
    connect = fixture.APITests.connect
    conversation = fixture.APITests.conversation
    send = fixture.APITests.send

    async def prefs(self):
        response = await self.call('GET','/settings/quickui')
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    async def save_prefs(self, preferences, revision):
        return await self.call('PUT','/settings/quickui',json={'preferences':preferences,'revision':revision})

    async def test_preferences_isolation_revision_and_validation(self):
        initial=await self.prefs()
        self.assertEqual(initial['preferences']['behavior'],'automatic')
        preferences=initial['preferences']
        preferences['color']={'mode':'solid','colors':['#008800'],'angle':120,'stops':[0]}
        saved=await self.save_prefs(preferences,0)
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual((await self.prefs())['preferences']['color']['colors'],['#008800'])
        stale=await self.save_prefs(preferences,0)
        self.assertEqual(stale.status_code,409)
        other=await self.client.post('/auth/signup',json={'email':__import__('uuid').uuid4().hex+'@example.com','password':'password123'})
        other_headers={'Authorization':'Bearer '+other.json()['token']}
        theirs=await self.client.get('/settings/quickui',headers=other_headers)
        self.assertEqual(theirs.json()['revision'],0)
        self.assertEqual(theirs.json()['recent'],[])
        mine=(await self.prefs())['recent'][0]['id']
        self.assertEqual((await self.client.delete(f'/settings/quickui/palette/{mine}',headers=other_headers)).status_code,404)
        preferences['color']['colors']=['url(javascript:alert(1))']
        self.assertEqual((await self.save_prefs(preferences,1)).status_code,422)
        self.assertFalse(fixture.FakeClient.calls)

    async def test_canvas_preferences_additive_roundtrip_legacy_saves_and_validation(self):
        initial = await self.prefs()
        self.assertTrue(initial['preferences']['canvas']['inherit'])
        prefs = initial['preferences']
        prefs['canvas'].update(inherit=False, accent='#16804a', chart_colors=['#123456', '#654321'], density='compact')
        saved = await self.save_prefs(prefs, initial['revision'])
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((await self.prefs())['preferences']['canvas']['accent'], '#16804a')
        legacy = {k:v for k,v in prefs.items() if k != 'canvas'}
        legacy['density'] = 'spacious'
        saved = await self.save_prefs(legacy, saved.json()['revision'])
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['preferences']['canvas'], prefs['canvas'])
        self.assertEqual(saved.json()['preferences']['density'], 'spacious')
        self.assertEqual((await self.save_prefs(prefs, 0)).status_code, 409)
        for patch in ({'accent':'url(javascript:alert(1))'}, {'chart_colors':['red']}, {'chart_colors':[]}, {'density':'huge'}, {'widget_color':{'mode':'solid','colors':['<script>'],'stops':[0]}}):
            invalid = {**prefs, 'canvas':{**prefs['canvas'], **patch}}
            self.assertEqual((await self.save_prefs(invalid, saved.json()['revision'])).status_code, 422)
        self.assertFalse(fixture.FakeClient.calls)

    async def test_recent_colors_deduplicate_cap_order_and_delete(self):
        async def recent(n):
            color={'mode':'solid','colors':[f'#{n:06x}'],'angle':120,'stops':[0]}
            response=await self.call('POST','/settings/quickui/palettes/recent',json={'selection':color})
            self.assertEqual(response.status_code,200,response.text)
            return response.json()
        for n in range(20): await recent(n)
        result=await recent(10)
        self.assertEqual(len(result['recent']),16)
        self.assertEqual(result['recent'][0]['selection']['colors'],['#00000a'])
        pid=result['recent'][0]['id']
        self.assertEqual((await self.call('DELETE',f'/settings/quickui/palette/{pid}')).status_code,200)
        cleared=await self.call('DELETE','/settings/quickui/palettes/recent')
        self.assertEqual(cleared.json()['recent'],[])
        gradient={'mode':'gradient','colors':['#0044ff','#16804a'],'angle':45,'stops':[0,100]}
        saved=await self.call('POST','/settings/quickui/palettes/saved',json={'name':'Mine','selection':gradient})
        self.assertEqual(saved.json()['saved'][0]['selection'],gradient)
        self.assertEqual(saved.json()['recent'][0]['selection'],gradient)
        self.assertFalse(fixture.FakeClient.calls)

    async def test_specs_persist_and_appearance_never_regenerates(self):
        await self.connect(); cid=await self.conversation()
        async def visual_stream(client,**kwargs):
            fixture.FakeClient.calls.append(('stream',client.key,kwargs))
            async def chunks():
                for start in range(0,len(ANSWER),37):
                    yield NS(text=ANSWER[start:start+37],usage_metadata=None)
            return chunks()
        with patch.object(fixture.FakeClient,'generate_content_stream',visual_stream):
            response=await self.send(cid)
        message=fixture.events(response)[-1][1]['message']
        self.assertEqual(message['quickui']['title'],SPEC['title'])
        self.assertNotIn('```quickui',message['content'])
        self.assertEqual(message['quickui_intro'],'Here is a comparison.')
        count=len(fixture.FakeClient.calls)
        p=await self.prefs(); appearance=quickui.Appearance().model_dump()
        appearance['color']={'mode':'gradient','colors':['#0000ff','#7c3aed'],'angle':90,'stops':[0,100]}
        mid=message['id']
        for scope in [f'/conversations/{cid}/messages/{mid}/quickui-appearance',f'/conversations/{cid}/quickui-appearance']:
            r=await self.call('PUT',scope,json={'appearance':appearance})
            self.assertEqual(r.status_code,200,r.text)
        p['preferences']['color']={'mode':'solid','colors':['#008800'],'angle':120,'stops':[0]}
        await self.save_prefs(p['preferences'],p['revision'])
        reopened=(await self.call('GET',f'/conversations/{cid}')).json()
        self.assertEqual(reopened['messages'][-1]['quickui'],message['quickui'])
        self.assertEqual(reopened['quickui_appearance'],appearance)
        self.assertEqual(len(fixture.FakeClient.calls),count)
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(QuickUIResponse,mid))
            self.assertNotIn('appearance',db.get(QuickUIResponse,mid).specification)
        await self.call('DELETE',f'/conversations/{cid}')
        with SessionLocal() as db: self.assertIsNone(db.get(QuickUIResponse,mid))

    async def test_grounding_and_quickui_share_one_generation(self):
        await self.connect();cid=await self.conversation()
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.encrypted_api_key.is_not(None),User.email==(await self.call('GET','/auth/me')).json()['email']))
            user.preferred_model='gemini-2.5-flash';db.commit()
            model={'id':'gemini-2.5-flash','input_token_limit':100000,'output_token_limit':8192,'tier':'free','pricing_checked_at':fixture.main.now()}
            gemini._models_cache[gemini.cache_id(user)]=(float('inf'),[model])
        async def grounded(client,**kwargs):
            fixture.FakeClient.calls.append(('stream',client.key,kwargs))
            assert kwargs['config'].tools[0].google_search is not None
            assert 'QuickUI' in kwargs['config'].system_instruction
            async def chunks():
                yield NS(text=ANSWER,usage_metadata=NS(prompt_token_count=99,candidates_token_count=50,total_token_count=149),
                    candidates=[NS(grounding_metadata=types.GroundingMetadata(web_search_queries=['comparison'],grounding_chunks=[types.GroundingChunk(web=types.GroundingChunkWeb(uri='https://example.com',title='Source'))],grounding_supports=[types.GroundingSupport(segment=types.Segment(text='Here is a comparison.'),grounding_chunk_indices=[0])]))])
            return chunks()
        with patch.object(fixture.FakeClient,'generate_content_stream',grounded):
            r=await self.call('POST',f'/conversations/{cid}/messages',data={'text':'Compare','web_search':'true'})
        message=fixture.events(r)[-1][1]['message']
        self.assertTrue(message['quickui']);self.assertTrue(message['grounding']['grounded'])
        self.assertIn('[1](https://example.com)',message['content'])
        self.assertEqual(len([c for c in fixture.FakeClient.calls if c[0]=='stream']),1)
        usage=(await self.call('GET','/usage')).json()
        self.assertEqual(usage['totals']['reported_search_queries'],1)
        self.assertEqual(usage['totals']['input_tokens'],99)
        self.assertEqual(usage['totals']['quickui_responses'],1)
        self.assertIsNotNone(usage['recent_activity'][0]['latency_ms'])

    async def test_disabled_unsupported_and_ownership(self):
        await self.connect();cid=await self.conversation()
        r=await self.call('POST',f'/conversations/{cid}/messages',data={'text':'Hello','web_search':'true'})
        self.assertEqual(r.status_code,400)
        self.assertFalse([c for c in fixture.FakeClient.calls if c[0]=='stream'])
        r=await self.call('POST',f'/conversations/{cid}/messages',data={'text':'Hello','quickui_behavior':'disabled'})
        self.assertEqual(r.status_code,200,r.text)
        config=[c[2]['config'] for c in fixture.FakeClient.calls if c[0]=='stream'][-1]
        self.assertIsNone(config.tools)
        self.assertNotIn('QuickUI',config.system_instruction)
        r=await self.call('PUT','/conversations/1/quickui-appearance',json={'appearance':quickui.Appearance().model_dump()})
        self.assertEqual(r.status_code,404)
        r=await self.call('PUT',f'/conversations/{cid}/messages/1/quickui-appearance',json={'appearance':None})
        self.assertEqual(r.status_code,404)

    async def test_reset_keeps_monotonic_revision_and_migration_is_repeatable(self):
        p=await self.prefs(); p['preferences']['style']='playful'
        self.assertEqual((await self.save_prefs(p['preferences'],0)).status_code,200)
        r=await self.call('POST','/settings/quickui/reset',json={'preferences':p['preferences'],'revision':1})
        self.assertEqual(r.json()['preferences']['style'],'modern')
        self.assertEqual(r.json()['revision'],2)
        migrate();migrate()
        with SessionLocal() as db: self.assertEqual(db.get(Message,1).content,'Keep this original message')

    async def test_real_sdk_search_tool_serialization_and_no_json_mode(self):
        import httpx
        from google import genai
        sent=[]
        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'text':'Grounded answer'}]}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with genai.Client(api_key='AQ.mock-search-key',http_options=types.HttpOptions(httpx_async_client=http)).aio as sdk:
                result=await sdk.models.generate_content(model='gemini-2.5-flash',contents='Latest news',
                    config=gemini.generation_config({'id':'gemini-2.5-flash'},gemini.SYSTEM+quickui.PROMPT,web_search=True))
        self.assertEqual(result.text,'Grounded answer')
        self.assertEqual(sent[0]['tools'],[{'googleSearch':{}}])
        self.assertNotIn('responseMimeType',sent[0].get('generationConfig',{}))
        self.assertIn('QuickUI',sent[0]['systemInstruction']['parts'][0]['text'])

    async def test_grounding_error_does_not_retry_or_drop_user_message(self):
        await self.connect();cid=await self.conversation()
        with SessionLocal() as db:
            email=(await self.call('GET','/auth/me')).json()['email']
            user=db.scalar(select(User).where(User.email==email))
            user.preferred_model='gemini-2.5-flash';db.commit()
            gemini._models_cache[gemini.cache_id(user)]=(float('inf'),[{'id':'gemini-2.5-flash','tier':'free','pricing_checked_at':fixture.main.now(),'input_token_limit':100000,'output_token_limit':8192}])
        for code in (400,403,429):
            count=[]
            async def rejected(client,**kwargs):
                count.append(kwargs)
                raise fixture.ProviderError(code)
            with patch.object(fixture.FakeClient,'generate_content_stream',rejected):
                response=await self.call('POST',f'/conversations/{cid}/messages',data={'text':'Search for facts','web_search':'true'})
            frames=fixture.events(response)
            error=next(data for name,data in frames if name=='error')
            self.assertIn('Google',error['message'])
            self.assertEqual(len(count),1)
            self.assertEqual(frames[-1][1]['status'],'error')
        reopened=(await self.call('GET',f'/conversations/{cid}')).json()
        self.assertEqual(len(reopened['messages']),3)
        self.assertTrue(all(m['role']=='user' for m in reopened['messages']))

    async def test_concurrent_migrations_preserve_existing_database_rows(self):
        import os, sqlite3, subprocess, sys, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'concurrent.db'
            with sqlite3.connect(fixture.DB_PATH) as source,sqlite3.connect(path) as target:
                source.backup(target)
                target.execute('ALTER TABLE quickui_responses DROP COLUMN introduction')
            env={**os.environ,'DATABASE_URL':f'sqlite:///{path}'}
            processes=[subprocess.Popen([sys.executable,'-c','from app.database import migrate; migrate()'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
            for p in processes:
                _,error=p.communicate(timeout=15)
                self.assertEqual(p.returncode,0,error.decode())
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT content FROM messages WHERE id=1').fetchone()[0],'Keep this original message')
