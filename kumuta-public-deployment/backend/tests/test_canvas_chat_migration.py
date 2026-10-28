"""Populated v18 backup, transactional v19 failure/retry and legacy preservation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import patch
import test_api
from sqlalchemy import create_engine, text
from app import database, migrations


class CanvasChatMigrationTests(unittest.TestCase):
    def test_v18_upgrade_preserves_rows_and_rolls_back_interruption(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'v18.db';engine=create_engine(f'sqlite:///{path}')
            self.addCleanup(engine.dispose)
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=18},clear=True):database.migrate()
            with engine.begin() as db:
                import re
                definition=db.scalar(text("SELECT sql FROM sqlite_master WHERE name='canvas_generation_jobs'"))
                definition='\n'.join(line for line in definition.splitlines() if not any(name in line for name in ('user_message_id','assistant_message_id','reply_text')))
                definition=re.sub(r',\s*\)$','\n)',definition)
                db.exec_driver_sql('DROP TABLE canvas_generation_jobs')
                db.exec_driver_sql(definition)
                db.exec_driver_sql('ALTER TABLE users DROP COLUMN canvas_generation_mode')
                db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(1,'legacy@example.com','keep',0)")
                db.exec_driver_sql("INSERT INTO workspaces(id,owner_id,name,revision,created_at,updated_at) VALUES(1,1,'Keep',1,'','')")
                db.exec_driver_sql("INSERT INTO canvas_boards(id,owner_id,workspace_id,title,status,current_revision,created_at,updated_at) VALUES(1,1,1,'Keep','active',0,'','')")
                db.exec_driver_sql("INSERT INTO canvas_generation_jobs(id,owner_id,board_id,artifact_id,request_key,request_hash,prompt,engine,output_format,status,event_sequence,created_at,updated_at) VALUES('old',1,1,'a','key','hash','Keep prompt','B','openui-lang-v1','completed',1,'','')")
            upgrade=migrations.MIGRATIONS[19]
            def interrupted(db,stamp):upgrade(db,stamp);raise RuntimeError('v19 interruption')
            with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{19:interrupted}):
                with self.assertRaisesRegex(RuntimeError,'v19 interruption'):database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),18)
                self.assertNotIn('reply_text',{r[1] for r in db.exec_driver_sql('PRAGMA table_info(canvas_generation_jobs)')})
            with patch.object(database,'engine',engine):database.migrate();database.migrate()
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
                self.assertEqual(db.exec_driver_sql('SELECT prompt,output_format,reply_text,user_message_id FROM canvas_generation_jobs').one(),('Keep prompt','openui-lang-v1',None,None))
                self.assertEqual(db.scalar(text('SELECT canvas_generation_mode FROM users')),'auto')
                self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
            for backup in Path(directory).glob('*.bak'):
                self.assertEqual(backup.stat().st_mode&0o777,0o600)
                with sqlite3.connect(backup) as db:self.assertEqual(db.execute('SELECT prompt FROM canvas_generation_jobs').fetchone()[0],'Keep prompt')
