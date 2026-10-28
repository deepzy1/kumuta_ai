"""UX persistence contracts on disposable SQL databases, without providers."""
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from sqlalchemy import create_engine, text
from app import database, migrations
import test_api as fixture
import test_workspaces as workspace_fixture
import test_documents as document_fixture

class UXTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.APITests.asyncSetUp
    asyncTearDown = fixture.APITests.asyncTearDown
    call = fixture.APITests.call
    ok = workspace_fixture.WorkspaceAPITests.ok
    project = workspace_fixture.WorkspaceAPITests.project
    task = workspace_fixture.WorkspaceAPITests.task
    board_revision = workspace_fixture.WorkspaceAPITests.board_revision
    upload = document_fixture.DocumentTests.upload

    async def test_task_document_links_reject_other_projects_and_survive_reload(self):
        project, columns = await self.project('Task files')
        other, _ = await self.project('Other')
        task = await self.task(project, columns[0])
        doc = await self.upload(project_id=project['id'])
        foreign = await self.upload(project_id=other['id'])
        path = f'/projects/{project["id"]}/tasks/{task["id"]}'
        updated = await self.ok('PATCH', path, json={'revision': task['revision'], 'document_ids': [doc['id']]})
        self.assertEqual((await self.ok('GET', path))['document_ids'], [doc['id']])
        refs = (await self.ok('GET', f'/documents?project_id={project["id"]}'))['items'][0]['task_refs']
        self.assertEqual(refs, [{'id': task['id'], 'title': task['title']}])
        await self.ok('PATCH', path, status=404, json={'revision': updated['task']['revision'], 'document_ids': [foreign['id']]})
        await self.ok('PATCH', path, status=409, json={'revision': task['revision'], 'document_ids': []})
        await self.ok('DELETE', f'/documents/{doc["id"]}', json={'revision': doc['revision'], 'confirmation': 'DELETE'})
        self.assertEqual((await self.ok('GET', path))['document_ids'], [])
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_note_pin_and_revision_protect_autosave(self):
        project, _ = await self.project('Notes')
        path = f'/projects/{project["id"]}/notes'
        a = await self.ok('POST', path, status=201, json={'title': 'Pinned note', 'content': '- [ ] Keep this'})
        await self.ok('POST', path, status=201, json={'title': 'Other note'})
        a = await self.ok('PUT', f'{path}/{a["id"]}', json={'revision': a['revision'], 'title': a['title'], 'content': a['content'], 'pinned': True})
        listing = await self.ok('GET', path)
        self.assertEqual(listing['items'][0]['id'], a['id'])
        self.assertEqual(listing['items'][0]['excerpt'], '- [ ] Keep this')
        await self.ok('PUT', f'{path}/{a["id"]}', status=409, json={'revision': 1, 'title': 'Stale', 'content': ''})
        self.assertEqual((await self.ok('GET', f'{path}/{a["id"]}'))['content'], '- [ ] Keep this')
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_column_deletion_moves_tasks_and_preserves_content(self):
        project, columns = await self.project('Stages')
        task = await self.task(project, columns[0], description='Preserved task')
        path = f'/projects/{project["id"]}/columns/{columns[0]["id"]}'
        revision = await self.board_revision(project['id'])
        await self.ok('DELETE', path, status=422, json={'board_revision': revision})
        await self.ok('DELETE', path, json={'board_revision': revision, 'destination_id': columns[-1]['id']})
        saved = await self.ok('GET', f'/projects/{project["id"]}/tasks/{task["id"]}')
        self.assertEqual(saved['description'], 'Preserved task')
        self.assertEqual(saved['column_id'], columns[-1]['id'])
        self.assertTrue(saved['completed'])

class UXMigrationTests(unittest.TestCase):
    def test_populated_v12_rollback_retry_and_note_retention(self):
        with TemporaryDirectory() as folder:
            engine = create_engine(f'sqlite:///{folder}/upgrade.db')
            try:
                with patch.object(database, 'engine', engine): database.migrate()
                with engine.begin() as db:
                    db.exec_driver_sql('DELETE FROM schema_migrations WHERE version>=13')
                    db.exec_driver_sql('DROP TABLE task_documents')
                    db.exec_driver_sql('DROP INDEX ix_notes_project_pinned')
                    db.exec_driver_sql('ALTER TABLE project_notes DROP COLUMN pinned')
                    db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(1,'retained@test.com','kept',0)")
                    db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(1,1,'Kept',1,'','')")
                    db.exec_driver_sql("INSERT INTO projects(id,workspace_id,owner_id,name,description,icon,color,archived,revision,board_revision,created_at,updated_at) VALUES(1,1,1,'Kept','','folder','#ff6500',0,1,1,'','')")
                    db.exec_driver_sql("INSERT INTO project_notes(id,project_id,title,content,revision,created_at,updated_at) VALUES(1,1,'Kept','Retained note',1,'','')")
                original = migrations.MIGRATIONS[13]
                def fail(c, t): original(c, t); raise RuntimeError('Interrupted UX migration')
                with patch.object(database, 'engine', engine), patch.dict(migrations.MIGRATIONS, {13: fail}):
                    with self.assertRaisesRegex(RuntimeError, 'Interrupted'): database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')), 12)
                    self.assertNotIn('pinned', [r[1] for r in db.exec_driver_sql('PRAGMA table_info(project_notes)')])
                with patch.object(database, 'engine', engine): database.migrate(); database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.execute(text('SELECT content,pinned FROM project_notes')).one(), ('Retained note', 0))
                    self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(), 'ok')
                    self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(), [])
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')), max(migrations.MIGRATIONS))
                for backup in Path(folder).glob('*.bak'): self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            finally: engine.dispose()
