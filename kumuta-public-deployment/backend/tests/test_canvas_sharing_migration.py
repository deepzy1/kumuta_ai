"""Populated v21 additive upgrade, backup, rollback and concurrent retry."""
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import test_api
from sqlalchemy import create_engine,text,event
from app import database,migrations

class SharingMigrationTests(unittest.TestCase):
    def test_populated_v21_preserves_private_boards_hashes_scenes_and_jobs(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'existing.db'
            engine=create_engine(f'sqlite:///{path}',connect_args={'check_same_thread':False,'timeout':15})
            self.addCleanup(engine.dispose)
            @event.listens_for(engine,'connect')
            def fk(connection,_):connection.execute('PRAGMA foreign_keys=ON')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=21},clear=True):database.migrate()
            with engine.begin() as db:
                db.exec_driver_sql('DROP TABLE canvas_board_members');db.exec_driver_sql('DROP TABLE browser_sessions')
                db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(99,'preserve@example.com','ORIGINAL HASH',0)")
                db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(99,99,'Original workspace',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_boards(id,owner_id,workspace_id,title,status,current_revision,created_at,updated_at) VALUES(99,99,99,'Private board','active',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_scene_revisions(board_id,revision,schema_version,scene_json,created_at) VALUES(99,1,1,'{\"elements\":[],\"artifacts\":[],\"private\":\"unchanged fixture\"}','')")
                db.exec_driver_sql("INSERT INTO canvas_generation_jobs(id,owner_id,board_id,artifact_id,request_key,request_hash,prompt,engine,output_format,status,event_sequence,created_at,updated_at) VALUES('old',99,99,'a','key','hash','Keep prompt','B','openui-lang-v1','completed',1,'','')")
                before=db.exec_driver_sql('SELECT * FROM canvas_scene_revisions').all()
            def fail(db,stamp):migrations.canvas_sharing_sessions(db,stamp);raise RuntimeError('interrupted sharing upgrade')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{22:fail}):
                with self.assertRaisesRegex(RuntimeError,'interrupted'):database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),21)
                self.assertIsNone(db.scalar(text("SELECT name FROM sqlite_master WHERE name='canvas_board_members'")))
            with patch.object(database,'engine',engine):
                with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:database.migrate(),range(2)))
                database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
                self.assertEqual(db.exec_driver_sql('SELECT * FROM canvas_scene_revisions').all(),before)
                self.assertEqual(db.scalar(text('SELECT password_hash FROM users WHERE id=99')),'ORIGINAL HASH')
                self.assertEqual(db.scalar(text('SELECT prompt FROM canvas_generation_jobs')),'Keep prompt')
                self.assertEqual(db.scalar(text('SELECT count(*) FROM canvas_board_members')),0)
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
            backups=list(Path(directory).glob('*.bak'));self.assertEqual(len(backups),2)
            for backup in backups:
                self.assertEqual(backup.stat().st_mode&0o777,0o600)
                with sqlite3.connect(backup) as db:
                    self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],21)
                    self.assertEqual(db.execute('SELECT password_hash FROM users WHERE id=99').fetchone()[0],'ORIGINAL HASH')
