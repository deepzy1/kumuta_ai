"""Fresh/v13 SQLite migration, preservation, interruption and concurrent startup."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_api  # Isolated application configuration before any app imports.
from sqlalchemy import create_engine, event, text
from app import database, migrations


class BoardMigrationTests(unittest.TestCase):
    def engine(self, path):
        engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False, 'timeout': 15})
        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, _): connection.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(engine.dispose)
        return engine

    def test_fresh_database_repeatable_and_integrity(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'fresh.db'; engine = self.engine(path)
            with patch.object(database,'engine',engine): database.migrate(); database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
                self.assertEqual(db.scalar(text('SELECT count(*) FROM schema_migrations WHERE version=14')),1)
                self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name LIKE 'canvas_%'")),12)
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
            self.assertEqual(list(Path(directory).glob('*.bak')),[])

    def test_populated_v13_failure_rollback_retry_and_concurrent_upgrade(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'v13.db'; engine = self.engine(path)
            with patch.object(database,'engine',engine), patch.dict(migrations.MIGRATIONS,
                    {k:v for k,v in migrations.MIGRATIONS.items() if k<=13},clear=True): database.migrate()
            with engine.begin() as db:
                # Reconstruct the actual pre-Canvas schema, rather than leaving
                # today's metadata-created tables in a nominal version-13 DB.
                for name in ('canvas_board_members','canvas_board_media','canvas_artifact_render_reports','canvas_artifact_placements','canvas_artifact_versions','canvas_artifacts','canvas_generation_events','canvas_generation_jobs','canvas_board_resources','canvas_board_conversations','canvas_scene_revisions','canvas_boards'):
                    db.exec_driver_sql(f'DROP TABLE {name}')
                db.exec_driver_sql('DROP INDEX ux_projects_canvas_scope')
                db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(41,'legacy@local.test','keep hash',0)")
                db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(51,41,'Legacy workspace',1,'','')")
                db.exec_driver_sql("INSERT INTO projects(id,workspace_id,owner_id,name,description,icon,color,archived,revision,board_revision,created_at,updated_at) VALUES(61,51,41,'Legacy project','','folder','#ffffff',0,1,7,'','')")
                db.exec_driver_sql("INSERT INTO conversations(id,user_id,project_id,title,created_at,updated_at) VALUES(71,41,61,'Legacy chat','','')")
                db.exec_driver_sql("INSERT INTO messages(id,conversation_id,role,content,created_at,status,active) VALUES(81,71,'user','Keep original content','','complete',1)")
                db.exec_driver_sql("INSERT INTO document_files(id,storage_key,created_at) VALUES(91,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','')")
                db.exec_driver_sql("INSERT INTO documents(id,user_id,project_id,scope_key,file_id,filename,mime,size,sha256,status,pages,chunk_count,attempts,revision,created_at,updated_at) VALUES(101,41,61,'project:61',91,'legacy.txt','text/plain',12,'bbbb','ready',1,1,1,1,'','')")
                db.exec_driver_sql("INSERT INTO document_chunks(id,document_id,ordinal,section,content) VALUES(111,101,0,'Original','Preserved needle evidence')")
            upgrade = migrations.MIGRATIONS[14]
            def interrupt(connection,timestamp):
                upgrade(connection,timestamp)
                raise RuntimeError('Canvas migration interruption')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{14:interrupt}):
                with self.assertRaisesRegex(RuntimeError,'Canvas migration interruption'): database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),13)
                self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE name LIKE 'canvas_%'")),0)
                self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE name='ux_projects_canvas_scope'")),0)
            with patch.object(database,'engine',engine):
                with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(lambda _:database.migrate(),range(2)))
                database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
                self.assertEqual(db.scalar(text('SELECT password_hash FROM users WHERE id=41')),'keep hash')
                self.assertEqual(db.scalar(text('SELECT content FROM messages WHERE id=81')),'Keep original content')
                self.assertEqual(db.scalar(text('SELECT board_revision FROM projects WHERE id=61')),7)
                self.assertEqual(db.scalar(text("SELECT count(*) FROM document_fts WHERE document_fts MATCH 'needle'")),1)
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
            backups=list(Path(directory).glob('*.bak'));self.assertEqual(len(backups),2)
            for backup in backups:
                self.assertEqual(backup.stat().st_mode&0o777,0o600)
                with sqlite3.connect(backup) as db:
                    self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],13)
                    self.assertEqual(db.execute('SELECT content FROM messages WHERE id=81').fetchone()[0],'Keep original content')
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
