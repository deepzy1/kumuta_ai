"""Explicit memory and context contracts against disposable SQLite, fake Gemini."""
import json
import unittest
from unittest.mock import patch

from sqlalchemy import select, text

import test_api as fixture
import test_workspaces as workspace_fixture
from app import memory
from app.database import SessionLocal, User, Conversation
from app.memory_models import Memory


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.APITests.asyncSetUp
    asyncTearDown = fixture.APITests.asyncTearDown
    call = fixture.APITests.call
    connect = fixture.APITests.connect
    conversation = fixture.APITests.conversation
    send = fixture.APITests.send
    ok = workspace_fixture.WorkspaceAPITests.ok
    project = workspace_fixture.WorkspaceAPITests.project

    async def save(self, content='Prefer SQLite for storage', **scope):
        return await self.ok('POST', '/memories', status=201, json={'content': content, 'consent': True, **scope})

    async def enable(self, enabled=True, **scope):
        data = {'scope': 'global', **scope}
        from urllib.parse import urlencode
        current = await self.ok('GET', '/settings/memory?' + urlencode(data))
        return await self.ok('PUT', '/settings/memory', json={**data, 'enabled': enabled, 'revision': current['revision']})

    async def test_crud_consent_dedup_search_and_no_provider_calls(self):
        await self.ok('POST', '/memories', status=422, json={'content': 'missing consent'})
        await self.ok('POST', '/memories', status=422, json={'content': '   ', 'consent': True})
        first = await self.save()
        duplicate = await self.save('  PREFER   SQLite for storage  ')
        self.assertEqual(first['id'], duplicate['id'])
        self.assertTrue(duplicate['duplicate'])
        found = await self.ok('GET', '/memories?q=storage')
        self.assertEqual([r['id'] for r in found['items']], [first['id']])
        edited = await self.ok('PATCH', f'/memories/{first["id"]}', json={'content': 'Prefer Python for services', 'consent': True, 'revision': 1})
        self.assertEqual((await self.ok('GET', '/memories?q=storage'))['items'], [])
        self.assertEqual(len((await self.ok('GET', '/memories?q=Python'))['items']), 1)
        await self.ok('PATCH', f'/memories/{first["id"]}', status=409, json={'content': 'stale', 'consent': True, 'revision': 1})
        await self.ok('DELETE', f'/memories/{first["id"]}', json={'revision': edited['revision']})
        self.assertEqual((await self.ok('GET', '/memories'))['items'], [])
        with SessionLocal() as db:
            self.assertFalse(db.scalar(text('SELECT count(*) FROM memory_fts WHERE rowid=:id'), {'id': first['id']}))
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_scopes_isolation_confirmation_and_cascade(self):
        a, _ = await self.project('A'); b, _ = await self.project('B')
        cid, other = await self.conversation(), await self.conversation()
        global_row = await self.save('global SQLite')
        project_row = await self.save('project SQLite', scope='project', project_id=a['id'])
        chat_row = await self.save('chat SQLite', scope='conversation', conversation_id=cid)
        self.assertEqual((await self.ok('GET', f'/memories?scope=project&project_id={b["id"]}'))['items'], [])
        self.assertEqual((await self.ok('GET', f'/memories?scope=conversation&conversation_id={other}'))['items'], [])
        await self.ok('POST', '/memories/clear', status=422, json={'scope': 'global', 'confirmation': 'yes'})
        await self.ok('POST', '/memories/clear', json={'scope': 'project', 'project_id': a['id'], 'confirmation': 'CLEAR'})
        self.assertEqual(len((await self.ok('GET', '/memories?scope=all'))['items']), 2)
        await self.ok('DELETE', f'/conversations/{cid}')
        with SessionLocal() as db:
            self.assertIsNone(db.get(Memory, chat_row['id']))
            self.assertIsNone(db.get(Memory, project_row['id']))
            self.assertIsNotNone(db.get(Memory, global_row['id']))
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_other_user_id_tampering_and_settings(self):
        project, _ = await self.project()
        cid = await self.conversation()
        row = await self.save(scope='project', project_id=project['id'])
        other = await self.client.post('/auth/signup', json={'email': __import__('uuid').uuid4().hex + '@example.com', 'password': 'password123'})
        self.headers = {'Authorization': 'Bearer ' + other.json()['token']}
        for method, path, kwargs in [
            ('GET', f'/memories?scope=project&project_id={project["id"]}', {}),
            ('GET', f'/settings/memory?scope=conversation&conversation_id={cid}', {}),
            ('PATCH', f'/memories/{row["id"]}', {'json': {'content': 'tamper', 'consent': True, 'revision': 1}}),
            ('DELETE', f'/memories/{row["id"]}', {'json': {'revision': 1}}),
            ('POST', '/memories', {'json': {'scope': 'project', 'project_id': project['id'], 'content': 'tamper', 'consent': True}}),
        ]:
            await self.ok(method, path, status=404, **kwargs)
        self.assertEqual((await self.ok('GET', '/memories?scope=all'))['items'], [])
        self.assertFalse((await self.ok('GET', '/settings/memory'))['enabled'])
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_gemini_context_master_project_and_conversation_controls(self):
        await self.connect()
        project, _ = await self.project()
        other, _ = await self.project('Other')
        cid = (await self.ok('POST', '/conversations', json={'project_id': project['id']}))['id']
        await self.save('SQLite global fact')
        await self.save('SQLite project fact', scope='project', project_id=project['id'])
        await self.save('SQLite forbidden other project', scope='project', project_id=other['id'])
        await self.save('SQLite conversation fact', scope='conversation', conversation_id=cid)
        await self.send(cid, 'SQLite choices')
        last = next(c[2] for c in reversed(fixture.FakeClient.calls) if c[0] == 'stream')
        self.assertNotIn('UNTRUSTED SAVED MEMORY', str(last['contents']))
        await self.enable()
        await self.send(cid, 'SQLite choices')
        last = next(c[2] for c in reversed(fixture.FakeClient.calls) if c[0] == 'stream')
        contents = str(last['contents'])
        self.assertIn('SQLite global fact', contents)
        self.assertIn('SQLite project fact', contents)
        self.assertIn('SQLite conversation fact', contents)
        self.assertNotIn('forbidden other project', contents)
        self.assertNotIn('SQLite global fact', last['config'].system_instruction)
        await self.enable(False, scope='project', project_id=project['id'])
        await self.send(cid, 'SQLite choices')
        last = next(c[2] for c in reversed(fixture.FakeClient.calls) if c[0] == 'stream')
        self.assertNotIn('SQLite project fact', str(last['contents']))
        self.assertIn('SQLite global fact', str(last['contents']))
        await self.enable(False)
        await self.send(cid, 'SQLite choices')
        last = next(c[2] for c in reversed(fixture.FakeClient.calls) if c[0] == 'stream')
        self.assertNotIn('UNTRUSTED SAVED MEMORY', str(last['contents']))

    async def test_relevance_dedup_and_conservative_budget(self):
        cid = await self.conversation()
        await self.save('Python relevant preference')
        await self.save('Python relevant preference', scope='conversation', conversation_id=cid)
        await self.save('unrelated mango gardening')
        await self.save('Python ' + '🧡' * 300)
        await self.enable()
        with SessionLocal() as db, patch.object(memory, 'CONTEXT_BUDGET', 250):
            conversation = db.get(Conversation, cid); user = db.get(User, conversation.user_id)
            content, ids = memory.context(conversation, user, 'Python', db)
            self.assertLessEqual(len(content.encode()), 250)
            self.assertEqual(content.count('Python relevant preference'), 1)
            self.assertNotIn('mango', content)
            self.assertEqual(len(ids), 1)
            self.assertEqual(memory.context(conversation, user, 'nonsense-no-match', db), ('', []))
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_fts_input_and_setting_conflicts(self):
        await self.save('SQLite preference')
        for q in ['" OR *', "'); DROP TABLE users;--", 'sqlite NOT other', '\u0000']:
            from urllib.parse import quote
            await self.ok('GET', '/memories?q=' + quote(q))
        await self.enable()
        await self.ok('PUT', '/settings/memory', status=409, json={'scope': 'global', 'enabled': False, 'revision': 0})
        await self.ok('POST', '/memories', status=422, json={'scope': 'global', 'project_id': 1, 'content': 'x', 'consent': True})
