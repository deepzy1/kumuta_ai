"""Workspace contracts use the existing disposable DB and fake Google boundary."""
import asyncio
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, select, text

import test_api as fixture
from app import database, workspaces
from app.database import Conversation, Message, SessionLocal, User
from app.migrations import MIGRATIONS
from app.workspace_models import ChecklistItem, Note, Project, Task, TaskColumn, Workspace, WorkspaceMember


class WorkspaceAPITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.APITests.asyncSetUp
    asyncTearDown = fixture.APITests.asyncTearDown
    call = fixture.APITests.call
    connect = fixture.APITests.connect
    conversation = fixture.APITests.conversation
    send = fixture.APITests.send

    async def ok(self, method, path, status=200, **kwargs):
        response = await self.call(method, path, **kwargs)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    async def project(self, name='Test project', wid=None):
        if wid is None:
            wid = (await self.ok('GET', '/workspaces'))['items'][0]['id']
        project = await self.ok('POST', f'/workspaces/{wid}/projects', status=201, json={'name': name, 'description': 'Use a local SQLite database'})
        columns = (await self.ok('GET', f'/projects/{project["id"]}/columns'))['items']
        return project, columns

    async def task(self, project, column, title='Task', **values):
        return (await self.ok('POST', f'/projects/{project["id"]}/tasks', status=201,
                              json={'title': title, 'column_id': column['id'], **values}))['task']

    async def board_revision(self, pid):
        return (await self.ok('GET', f'/projects/{pid}'))['board_revision']

    async def move(self, project, task, column, before=None):
        return await self.ok('POST', f'/projects/{project["id"]}/tasks/{task["id"]}/move', json={
            'column_id': column['id'], 'before_id': before, 'board_revision': await self.board_revision(project['id'])})

    async def test_personal_workspace_signup_crud_pagination_and_zero_ai(self):
        listing = await self.ok('GET', '/workspaces')
        self.assertEqual(len(listing['items']), 1)
        personal = listing['items'][0]
        self.assertTrue(personal['is_personal'])
        with SessionLocal() as db:
            row = db.get(Workspace, personal['id'])
            self.assertIsNotNone(db.get(WorkspaceMember, (row.id, row.owner_id)))
        await self.ok('DELETE', f'/workspaces/{personal["id"]}', status=409, json={'revision': 1, 'confirm_name': personal['name']})
        new = await self.ok('POST', '/workspaces', status=201, json={'name': ' Work '})
        self.assertEqual(new['name'], 'Work')
        edited = await self.ok('PATCH', f'/workspaces/{new["id"]}', json={'name': 'Client work', 'revision': 1})
        self.assertEqual(edited['revision'], 2)
        await self.ok('PATCH', f'/workspaces/{new["id"]}', status=409, json={'name': 'Old edit', 'revision': 1})
        page = await self.ok('GET', '/workspaces?limit=1')
        self.assertTrue(page['has_more'])
        self.assertEqual((await self.ok('GET', '/workspaces?q=Client'))['items'][0]['id'], new['id'])
        await self.ok('DELETE', f'/workspaces/{new["id"]}', status=422, json={'revision': 2, 'confirm_name': 'wrong'})
        await self.ok('DELETE', f'/workspaces/{new["id"]}', json={'revision': 2, 'confirm_name': 'Client work'})
        self.assertEqual(len((await self.ok('GET', '/workspaces'))['items']), 1)
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_project_archive_restore_and_search(self):
        project, columns = await self.project('Alpha')
        self.assertEqual([c['name'] for c in columns], ['No Status', 'To Do', 'In Progress', 'Done'])
        pid, wid = project['id'], project['workspace_id']
        await self.project('Beta', wid)
        page = await self.ok('GET', f'/workspaces/{wid}/projects?sort=name&limit=1')
        self.assertTrue(page['has_more'])
        self.assertEqual(page['items'][0]['name'], 'Alpha')
        body = {'revision': 1, 'name': 'Alpha updated', 'description': 'Special context', 'color': '#000000', 'icon': 'code', 'archived': True}
        archived = await self.ok('PATCH', f'/projects/{pid}', json=body)
        self.assertEqual(archived['revision'], 2)
        self.assertEqual((await self.ok('GET', f'/workspaces/{wid}/projects?archived=true&q=special'))['items'][0]['id'], pid)
        await self.ok('POST', f'/projects/{pid}/tasks', status=409, json={'title': 'Blocked', 'column_id': columns[0]['id']})
        await self.ok('POST', f'/projects/{pid}/notes', status=409, json={'title': 'Blocked'})
        await self.ok('POST', '/conversations', status=409, json={'project_id': pid})
        await self.ok('PATCH', f'/projects/{pid}', status=409, json=body)
        await self.ok('PATCH', f'/projects/{pid}', json={**body, 'revision': 2, 'archived': False})
        partial = await self.ok('PATCH', f'/projects/{pid}', json={'revision': 3, 'name': 'Renamed'})
        self.assertEqual(partial['description'], 'Special context')
        self.assertEqual(partial['color'], '#000000')
        await self.task(project, columns[0])
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_tasks_checklists_subtasks_filters_and_revisions(self):
        project, columns = await self.project()
        pid = project['id']
        task = await self.task(project, columns[0], title='Important work', priority='high', due_date='2026-10-20')
        path = f'/projects/{pid}/tasks/{task["id"]}'
        edited = (await self.ok('PATCH', path, json={'revision': 1, 'description': 'Unique details', 'checklist': [
            {'text': 'First', 'completed': True}, {'text': 'Second'}]}))['task']
        self.assertEqual(edited['completion_percentage'], 50)
        await self.ok('PATCH', path, status=409, json={'revision': 1, 'title': 'Stale'})
        sub = await self.task(project, columns[3], parent_id=task['id'])
        current = await self.ok('GET', path)
        self.assertEqual(current['subtask_count'], 1)
        self.assertEqual(current['completion_percentage'], 67)
        await self.ok('POST', f'/projects/{pid}/tasks', status=422, json={'title': 'Too deep', 'column_id': columns[0]['id'], 'parent_id': sub['id']})
        page = await self.ok('GET', f'/projects/{pid}/tasks?q=unique&priority=high&due_before=2026-10-21&roots_only=true')
        self.assertEqual([t['id'] for t in page['items']], [task['id']])
        cleared = (await self.ok('PATCH', path, json={'revision': edited['revision'], 'due_date': None}))['task']
        self.assertIsNone(cleared['due_date'])
        await self.ok('DELETE', path, json={'revision': cleared['revision']})
        await self.ok('GET', f'/projects/{pid}/tasks/{sub["id"]}', status=404)
        with SessionLocal() as db:
            self.assertFalse(list(db.scalars(select(ChecklistItem).where(ChecklistItem.task_id == task['id']))))
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_ordering_moves_conflicts_and_normalization(self):
        project, columns = await self.project()
        pid = project['id']
        a = await self.task(project, columns[0], 'A')
        b = await self.task(project, columns[0], 'B')
        c = await self.task(project, columns[0], 'C')
        await self.move(project, c, columns[0], b['id'])
        listed = (await self.ok('GET', f'/projects/{pid}/tasks'))['items']
        self.assertEqual([t['id'] for t in listed], [a['id'], c['id'], b['id']])
        self.assertEqual(listed[0]['position'], a['position'])
        self.assertEqual(listed[2]['position'], b['position'])
        stale_revision = await self.board_revision(pid)
        moved = await self.move(project, a, columns[3])
        self.assertTrue(moved['task']['completed'])
        await self.ok('POST', f'/projects/{pid}/tasks/{b["id"]}/move', status=409, json={
            'column_id': columns[3]['id'], 'board_revision': stale_revision})
        # Force a small gap to exercise the infrequent normalization path.
        with SessionLocal() as db:
            db.get(Task, c['id']).position = 1
            db.get(Task, b['id']).position = 1 + 1e-9
            db.commit()
        await self.move(project, a, columns[0], b['id'])
        listed = (await self.ok('GET', f'/projects/{pid}/tasks'))['items']
        self.assertEqual([t['id'] for t in listed], [c['id'], a['id'], b['id']])
        self.assertEqual([t['position'] for t in listed], [1024, 2048, 3072])
        revision = await self.board_revision(pid)
        await self.ok('POST', f'/projects/{pid}/columns/{columns[3]["id"]}/move', json={
            'before_id': columns[0]['id'], 'board_revision': revision})
        self.assertEqual((await self.ok('GET', f'/projects/{pid}/columns'))['items'][0]['id'], columns[3]['id'])
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_custom_columns_and_completion_changes(self):
        project, columns = await self.project()
        pid = project['id']
        custom = (await self.ok('POST', f'/projects/{pid}/columns', status=201, json={
            'name': 'Review', 'board_revision': 1}))['column']
        task = await self.task(project, custom)
        await self.ok('PATCH', f'/projects/{pid}/columns/{custom["id"]}', json={
            'name': 'Shipped', 'is_done': True, 'board_revision': await self.board_revision(pid)})
        changed = await self.ok('GET', f'/projects/{pid}/tasks/{task["id"]}')
        self.assertTrue(changed['completed'])
        self.assertEqual(changed['revision'], task['revision'] + 1)
        renamed = await self.ok('PATCH', f'/projects/{pid}/columns/{custom["id"]}', json={
            'name': 'Completed', 'board_revision': await self.board_revision(pid)})
        self.assertTrue(renamed['column']['is_done'])

    async def test_concurrent_moves_only_accept_one_board_revision(self):
        project, columns = await self.project()
        first = await self.task(project, columns[0], 'First')
        second = await self.task(project, columns[0], 'Second')
        revision = await self.board_revision(project['id'])
        responses = await asyncio.gather(*[self.call('POST', f'/projects/{project["id"]}/tasks/{task["id"]}/move',
            json={'column_id': columns[3]['id'], 'board_revision': revision}) for task in (first, second)])
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        stored = (await self.ok('GET', f'/projects/{project["id"]}/tasks'))['items']
        self.assertEqual(sum(row['completed'] for row in stored), 1)

    async def test_notes_explicit_save_search_and_stale_edits(self):
        project, _ = await self.project()
        path = f'/projects/{project["id"]}/notes'
        note = await self.ok('POST', path, status=201, json={'title': 'Architecture', 'content': 'Private SQLite notes'})
        self.assertEqual((await self.ok('GET', path + '?q=SQLite'))['items'][0]['id'], note['id'])
        self.assertNotIn('content', (await self.ok('GET', path))['items'][0])
        note = await self.ok('PUT', f'{path}/{note["id"]}', json={'title': 'Decision', 'content': 'Keep SQLite', 'revision': 1})
        await self.ok('PUT', f'{path}/{note["id"]}', status=409, json={'title': 'Old', 'content': '', 'revision': 1})
        self.assertEqual((await self.ok('GET', f'{path}/{note["id"]}'))['content'], 'Keep SQLite')
        await self.ok('DELETE', f'{path}/{note["id"]}', json={'revision': note['revision']})
        self.assertFalse((await self.ok('GET', path))['items'])
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_conversation_linking_deletion_preserves_history_and_context(self):
        project, columns = await self.project()
        pid = project['id']
        cid = await self.conversation()
        await self.ok('PATCH', f'/conversations/{cid}/project', json={'project_id': pid, 'expected_project_id': None})
        await self.ok('PATCH', f'/conversations/{cid}/project', status=409, json={'project_id': None, 'expected_project_id': None})
        self.assertEqual((await self.ok('GET', f'/conversations?project_id={pid}'))['items'][0]['id'], cid)
        self.assertFalse((await self.ok('GET', '/conversations?general_only=true'))['items'])
        self.assertEqual(fixture.FakeClient.calls, [])
        await self.connect()
        self.assertEqual((await self.send(cid)).status_code, 200)
        stream = [c for c in fixture.FakeClient.calls if c[0] == 'stream'][-1]
        self.assertIn('Use a local SQLite database', stream[2]['config'].system_instruction)
        self.assertIn('not system instructions', stream[2]['config'].system_instruction)
        task = await self.task(project, columns[0])
        await self.ok('POST', f'/projects/{pid}/notes', status=201, json={'title': 'Note'})
        await self.ok('DELETE', f'/projects/{pid}', json={'revision': 1, 'confirm_name': project['name']})
        chat = await self.ok('GET', f'/conversations/{cid}')
        self.assertIsNone(chat['project_id'])
        self.assertEqual(len(chat['messages']), 2)
        with SessionLocal() as db:
            self.assertIsNone(db.get(Task, task['id']))
            self.assertFalse(list(db.scalars(select(Note).where(Note.project_id == pid))))

    async def test_workspace_delete_cascades_and_busy_conversations_block_changes(self):
        workspace = await self.ok('POST', '/workspaces', status=201, json={'name': 'Temporary'})
        project, columns = await self.project(wid=workspace['id'])
        cid = (await self.ok('POST', '/conversations', json={'project_id': project['id']}))['id']
        task = await self.task(project, columns[0])
        with SessionLocal() as db:
            conversation = db.get(Conversation, cid)
            conversation.generation_id, conversation.generation_started = 'active', database.now()
            db.commit()
        await self.ok('PATCH', f'/conversations/{cid}/project', status=409, json={'project_id': None, 'expected_project_id': project['id']})
        body = {'revision': 1, 'confirm_name': workspace['name']}
        await self.ok('DELETE', f'/workspaces/{workspace["id"]}', status=409, json=body)
        with SessionLocal() as db:
            db.get(Conversation, cid).generation_id = None
            db.commit()
        await self.ok('DELETE', f'/workspaces/{workspace["id"]}', json=body)
        self.assertIsNone((await self.ok('GET', f'/conversations/{cid}'))['project_id'])
        with SessionLocal() as db:
            self.assertIsNone(db.get(Project, project['id']))
            self.assertIsNone(db.get(Task, task['id']))

    async def test_cross_user_and_cross_project_ids_are_rejected(self):
        project, columns = await self.project()
        other, other_columns = await self.project('Second project')
        task = await self.task(project, columns[0])
        note = await self.ok('POST', f'/projects/{project["id"]}/notes', status=201, json={'title': 'Private'})
        pid, tid = project['id'], task['id']
        await self.ok('POST', f'/projects/{pid}/tasks', status=404, json={'title': 'Bad column', 'column_id': other_columns[0]['id']})
        await self.ok('POST', f'/projects/{other["id"]}/tasks', status=404, json={'title': 'Bad parent', 'column_id': other_columns[0]['id'], 'parent_id': tid})
        await self.ok('POST', f'/projects/{pid}/tasks/{tid}/move', status=404, json={
            'column_id': columns[0]['id'], 'before_id': 999999, 'board_revision': await self.board_revision(pid)})
        original_headers = self.headers
        signup = await self.client.post('/auth/signup', json={'email': __import__('uuid').uuid4().hex + '@example.com', 'password': 'password123'})
        self.headers = {'Authorization': 'Bearer ' + signup.json()['token']}
        for method, path, body in [
            ('GET', f'/workspaces/{project["workspace_id"]}/projects', None),
            ('PATCH', f'/workspaces/{project["workspace_id"]}', {'name': 'Steal', 'revision': 1}),
            ('POST', f'/workspaces/{project["workspace_id"]}/projects', {'name': 'Steal'}),
            ('GET', f'/projects/{pid}', None),
            ('PATCH', f'/projects/{pid}', {'name': 'Steal', 'revision': 1}),
            ('DELETE', f'/projects/{pid}', {'confirm_name': project['name'], 'revision': 1}),
            ('GET', f'/projects/{pid}/columns', None),
            ('POST', f'/projects/{pid}/columns', {'name': 'Steal', 'board_revision': 2}),
            ('PATCH', f'/projects/{pid}/columns/{columns[0]["id"]}', {'name': 'Steal', 'board_revision': 2}),
            ('POST', f'/projects/{pid}/columns/{columns[0]["id"]}/move', {'board_revision': 2}),
            ('GET', f'/projects/{pid}/tasks', None),
            ('GET', f'/projects/{pid}/tasks/{tid}', None),
            ('POST', f'/projects/{pid}/tasks', {'title': 'Steal', 'column_id': columns[0]['id']}),
            ('PATCH', f'/projects/{pid}/tasks/{tid}', {'title': 'Steal', 'revision': 1}),
            ('DELETE', f'/projects/{pid}/tasks/{tid}', {'revision': 1}),
            ('POST', f'/projects/{pid}/tasks/{tid}/move', {'column_id': columns[0]['id'], 'board_revision': 2}),
            ('GET', f'/projects/{pid}/notes', None),
            ('GET', f'/projects/{pid}/notes/{note["id"]}', None),
            ('POST', f'/projects/{pid}/notes', {'title': 'Steal'}),
            ('PUT', f'/projects/{pid}/notes/{note["id"]}', {'title': 'Steal', 'revision': 1}),
            ('DELETE', f'/projects/{pid}/notes/{note["id"]}', {'revision': 1}),
            ('GET', f'/conversations?project_id={pid}', None),
            ('POST', '/conversations', {'project_id': pid}),
        ]:
            with self.subTest(path=path, method=method):
                await self.ok(method, path, status=404, **({'json': body} if body is not None else {}))
        own_chat = await self.conversation()
        await self.ok('PATCH', f'/conversations/{own_chat}/project', status=404, json={'project_id': pid, 'expected_project_id': None})
        self.headers = original_headers
        await self.ok('PATCH', f'/conversations/{own_chat}/project', status=404, json={'project_id': pid, 'expected_project_id': None})
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_invalid_inputs_and_authentication(self):
        project, columns = await self.project()
        pid = project['id']
        for method, path, body in [
            ('POST', '/workspaces', {'name': '   '}),
            ('POST', '/workspaces', {'name': 'Name', 'owner_id': 1}),
            ('POST', f'/workspaces/{project["workspace_id"]}/projects', {'name': 'X', 'color': 'url(evil)'}),
            ('POST', f'/projects/{pid}/tasks', {'title': 'X', 'column_id': columns[0]['id'], 'due_date': '2026-02-31'}),
            ('POST', f'/projects/{pid}/tasks', {'title': 'X', 'column_id': columns[0]['id'], 'priority': 'bad'}),
            ('POST', f'/projects/{pid}/notes', {'title': 'X', 'content': 'a' * 100001}),
        ]:
            await self.ok(method, path, status=422, json=body)
        self.assertIn((await self.client.get('/workspaces')).status_code, (401, 403))


class WorkspaceMigrationTests(unittest.TestCase):
    def test_failed_data_migration_rolls_back_schema_and_can_retry(self):
        from app.migrations import MIGRATIONS
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'failed.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL, password_hash TEXT NOT NULL)')
                db.execute("INSERT INTO users VALUES (1, 'preserve@example.com', 'original')")
            engine = create_engine(f'sqlite:///{path}')
            try:
                with patch.object(database, 'engine', engine):
                    with patch.dict(MIGRATIONS, {3: lambda *_: (_ for _ in ()).throw(RuntimeError('simulated failure'))}):
                        with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
                            database.migrate()
                    with engine.connect() as db:
                        self.assertEqual(db.scalar(text('SELECT password_hash FROM users')), 'original')
                        self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE name='workspaces'")), 0)
                        self.assertNotIn('encrypted_api_key', [r[1] for r in db.execute(text('PRAGMA table_info(users)'))])
                    database.migrate()
                    with engine.connect() as db:
                        self.assertEqual(db.scalar(text('SELECT count(*) FROM workspaces')), 1)
            finally:
                engine.dispose()

    def test_standalone_migration_command_creates_fresh_database(self):
        import os
        import subprocess
        import sys
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'fresh.db'
            result = subprocess.run([sys.executable, '-m', 'app.migrate'], cwd=Path(__file__).resolve().parents[1],
                                    env={**os.environ, 'DATABASE_URL': f'sqlite:///{path}'}, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0], max(MIGRATIONS))
                self.assertEqual(db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 0)

    def test_v3_backfill_backup_repeatability_and_concurrent_startup(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.db'
            with sqlite3.connect(path) as db:
                db.executescript('''
                    CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL, password_hash TEXT NOT NULL);
                    INSERT INTO users VALUES (42, 'preserved@example.com', 'original-hash');
                    CREATE TABLE conversations (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL);
                    INSERT INTO conversations VALUES (51, 42, 'Original');
                    CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL, role TEXT NOT NULL,
                        content TEXT NOT NULL, attachment_name TEXT, attachment_mime TEXT, attachment_data TEXT);
                    INSERT INTO messages VALUES (61, 51, 'user', 'Original content', 'old.pdf', 'application/pdf', 'unchanged-bytes');
                ''')
            engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False, 'timeout': 10})
            try:
                with patch.object(database, 'engine', engine):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        list(pool.map(lambda _: database.migrate(), range(2)))
                    database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT count(*) FROM workspaces')), 1)
                    self.assertEqual(db.scalar(text('SELECT personal_owner_id FROM workspaces')), 42)
                    self.assertEqual(db.scalar(text('SELECT count(*) FROM workspace_members')), 1)
                    self.assertEqual(db.scalar(text('SELECT password_hash FROM users')), 'original-hash')
                    self.assertEqual(db.scalar(text('SELECT attachment_data FROM messages')), 'unchanged-bytes')
                    self.assertIsNone(db.scalar(text('SELECT project_id FROM conversations')))
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')), max(MIGRATIONS))
                backups = list(Path(folder).glob('*.bak'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
                with sqlite3.connect(backups[0]) as backup:
                    self.assertEqual(backup.execute('SELECT content FROM messages').fetchone()[0], 'Original content')
                    self.assertNotIn('project_id', [r[1] for r in backup.execute('PRAGMA table_info(conversations)')])
            finally:
                engine.dispose()

    def test_database_foreign_keys_prevent_cross_project_references(self):
        from sqlalchemy.exc import IntegrityError
        from app.workspace_schemas import ProjectCreate
        with SessionLocal() as db:
            self.assertEqual(db.scalar(text('PRAGMA foreign_keys')), 1)
            user = db.get(User, 1)
            workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
            first = workspaces.create_project(workspace, ProjectCreate(name='First'), db)
            second = workspaces.create_project(workspace, ProjectCreate(name='Second'), db)
            column = db.scalar(select(TaskColumn).where(TaskColumn.project_id == second.id))
            db.add(Task(project_id=first.id, column_id=column.id, title='Invalid', created_by=user.id, position=1024))
            with self.assertRaises(IntegrityError):
                db.flush()
            db.rollback()
