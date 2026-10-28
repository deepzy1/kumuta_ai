"""Actual v14 upgrade, backups, failed v15 rollback and concurrent restart."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import patch
import test_api
from sqlalchemy import create_engine, event, text
from app import database, migrations

TABLES=('canvas_artifact_render_reports','canvas_artifact_placements','canvas_artifact_versions',
        'canvas_artifacts','canvas_generation_events','canvas_generation_jobs')


class GenerationMigrationTests(unittest.TestCase):
    def test_populated_v14_upgrade_backup_rollback_repeat_and_integrity(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'v14.db'
            engine=create_engine(f'sqlite:///{path}',connect_args={'check_same_thread':False,'timeout':15})
            self.addCleanup(engine.dispose)
            @event.listens_for(engine,'connect')
            def foreign_keys(db,_):db.execute('PRAGMA foreign_keys=ON')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=14},clear=True):database.migrate()
            with engine.begin() as db:
                for name in TABLES:db.exec_driver_sql(f'DROP TABLE {name}')
                db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(1,'legacy@example.com','unchanged',0)")
                db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(1,1,'Legacy',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_boards(id,owner_id,workspace_id,title,status,current_revision,created_at,updated_at) VALUES(1,1,1,'Keep board','active',1,'','')")
                db.exec_driver_sql('INSERT INTO canvas_scene_revisions(board_id,revision,schema_version,scene_json,created_at) VALUES(1,1,1,\'{"type":"excalidraw","version":2,"elements":[],"artifacts":[]}\',\'\')')
            upgrade=migrations.MIGRATIONS[15]
            def fail(db,timestamp):upgrade(db,timestamp);raise RuntimeError('v15 interruption')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{15:fail}):
                with self.assertRaisesRegex(RuntimeError,'v15 interruption'):database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),14)
                self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE name='canvas_generation_jobs'")),0)
            with patch.object(database,'engine',engine):
                with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:database.migrate(),range(2)))
                database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
                self.assertEqual(db.scalar(text('SELECT title FROM canvas_boards WHERE id=1')),'Keep board')
                self.assertIn('"artifacts":[]',db.scalar(text('SELECT scene_json FROM canvas_scene_revisions')))
                self.assertEqual(db.scalar(text('SELECT password_hash FROM users')),'unchanged')
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
            backups=list(Path(directory).glob('*.bak'));self.assertEqual(len(backups),2)
            for backup in backups:
                self.assertEqual(backup.stat().st_mode&0o777,0o600)
                with sqlite3.connect(backup) as db:
                    self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],14)
                    self.assertEqual(db.execute('SELECT title FROM canvas_boards').fetchone()[0],'Keep board')


    def test_populated_v15_chat_link_upgrade_is_backed_up_atomic_and_repeatable(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'v15.db'
            engine=create_engine(f'sqlite:///{path}',connect_args={'check_same_thread':False,'timeout':15})
            self.addCleanup(engine.dispose)
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=15},clear=True):database.migrate()
            with engine.begin() as db:
                import re
                definition=db.scalar(text("SELECT sql FROM sqlite_master WHERE name='canvas_generation_jobs'"))
                definition='\n'.join(line for line in definition.splitlines() if 'conversation_id' not in line and 'output_format' not in line)
                definition=re.sub(r',\s*\)$','\n)',definition)
                db.exec_driver_sql('DROP TABLE canvas_generation_jobs')
                db.exec_driver_sql(definition)
                db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(1,'legacy@example.com','unchanged',0)")
                db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(1,1,'Legacy',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_boards(id,owner_id,workspace_id,title,status,current_revision,created_at,updated_at) VALUES(1,1,1,'Keep board','active',0,'','')")
                db.exec_driver_sql("INSERT INTO canvas_generation_jobs(id,owner_id,board_id,artifact_id,request_key,request_hash,prompt,engine,status,event_sequence,created_at,updated_at) VALUES('legacy',1,1,'artifact','legacy_key','hash','Keep prompt','B','completed',1,'','')")
            upgrade=migrations.MIGRATIONS[16]
            def fail(db,timestamp):upgrade(db,timestamp);raise RuntimeError('v16 interruption')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{16:fail}):
                with self.assertRaisesRegex(RuntimeError,'v16 interruption'):database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),15)
                self.assertNotIn('conversation_id',{r[1] for r in db.exec_driver_sql('PRAGMA table_info(canvas_generation_jobs)')})
            with patch.object(database,'engine',engine):
                with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:database.migrate(),range(2)))
                database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
                self.assertEqual(db.exec_driver_sql('SELECT prompt,conversation_id FROM canvas_generation_jobs').one(),('Keep prompt',None))
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
            for backup in Path(directory).glob('*.bak'):
                self.assertEqual(backup.stat().st_mode&0o777,0o600)
                with sqlite3.connect(backup) as db:self.assertEqual(db.execute('SELECT prompt FROM canvas_generation_jobs').fetchone()[0],'Keep prompt')

    def test_populated_v16_openui_upgrade_rollback_backup_and_legacy_default(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'v16.db'
            engine=create_engine(f'sqlite:///{path}')
            self.addCleanup(engine.dispose)
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=16},clear=True):database.migrate()
            with engine.begin() as db:
                db.exec_driver_sql('ALTER TABLE canvas_generation_jobs DROP COLUMN output_format')
                db.exec_driver_sql('ALTER TABLE canvas_generation_events DROP COLUMN preview_json')
                db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(1,'legacy@example.com','keep',0)")
                db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(1,1,'Keep',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_boards(id,owner_id,workspace_id,title,status,current_revision,created_at,updated_at) VALUES(1,1,1,'Keep','active',0,'','')")
                db.exec_driver_sql("INSERT INTO canvas_generation_jobs(id,owner_id,board_id,artifact_id,request_key,request_hash,prompt,engine,status,event_sequence,created_at,updated_at) VALUES('old',1,1,'a','key','hash','Keep prompt','B','queued',1,'','')")
            upgrade=migrations.MIGRATIONS[17]
            def fail(db,timestamp):upgrade(db,timestamp);raise RuntimeError('v17 interruption')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{17:fail}):
                with self.assertRaisesRegex(RuntimeError,'v17 interruption'):database.migrate()
            with engine.connect() as db:
                self.assertNotIn('output_format',{r[1] for r in db.exec_driver_sql('PRAGMA table_info(canvas_generation_jobs)')})
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),16)
            with patch.object(database,'engine',engine):database.migrate();database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.exec_driver_sql('SELECT prompt,output_format FROM canvas_generation_jobs').one(),('Keep prompt','kumuta-json-v1'))
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
            backups=list(Path(directory).glob('*.bak'));self.assertEqual(len(backups),2)
            for backup in backups:
                with sqlite3.connect(backup) as db:self.assertEqual(db.execute('SELECT prompt FROM canvas_generation_jobs').fetchone()[0],'Keep prompt')

    def test_already_applied_v17_missing_preview_column_is_repaired(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'partial-v17.db'
            engine=create_engine(f'sqlite:///{path}')
            self.addCleanup(engine.dispose)
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=17},clear=True):database.migrate()
            with engine.begin() as db:
                db.exec_driver_sql('ALTER TABLE canvas_generation_events DROP COLUMN preview_json')
                db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(1,'keep@example.com','keep',0)")
                db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(1,1,'Keep',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_boards(id,owner_id,workspace_id,title,status,current_revision,created_at,updated_at) VALUES(1,1,1,'Keep','active',0,'','')")
                db.exec_driver_sql("INSERT INTO canvas_generation_jobs(id,owner_id,board_id,artifact_id,request_key,request_hash,prompt,engine,status,event_sequence,created_at,updated_at) VALUES('old',1,1,'a','key','hash','Keep prompt','B','completed',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_generation_events(job_id,sequence,status,created_at) VALUES('old',1,'completed','')")
            upgrade=migrations.MIGRATIONS[18]
            def fail(db,timestamp):upgrade(db,timestamp);raise RuntimeError('v18 interruption')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{18:fail}):
                with self.assertRaisesRegex(RuntimeError,'v18 interruption'):database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),17)
                self.assertNotIn('preview_json',{r[1] for r in db.exec_driver_sql('PRAGMA table_info(canvas_generation_events)')})
            with patch.object(database,'engine',engine):database.migrate();database.migrate()
            with engine.begin() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
                self.assertEqual(db.exec_driver_sql('SELECT job_id,sequence,status,preview_json FROM canvas_generation_events').one(),('old',1,'completed',None))
                db.exec_driver_sql("INSERT INTO canvas_generation_events(job_id,sequence,status,preview_json,created_at) VALUES('old',2,'generating','{}','')")
                self.assertEqual(db.exec_driver_sql('SELECT prompt FROM canvas_generation_jobs').scalar(),'Keep prompt')
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
            backups=list(Path(directory).glob('*.bak'));self.assertEqual(len(backups),2)
            for backup in backups:
                self.assertEqual(backup.stat().st_mode&0o777,0o600)
                with sqlite3.connect(backup) as db:
                    self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],17)
                    self.assertEqual(db.execute('SELECT count(*) FROM canvas_generation_events').fetchone()[0],1)
