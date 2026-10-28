"""Schema 6 upgrade: private backup, rollback, retry and original-row retention."""
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import test_api as fixture
from sqlalchemy import create_engine, event, text
from app import database
from app.migrations import MIGRATIONS

class Phase2MigrationTests(unittest.TestCase):
    def test_schema6_upgrade_failure_retry_concurrent_repeat_and_retention(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'phase2.db'
            engine=create_engine(f'sqlite:///{path}',connect_args={'check_same_thread':False,'timeout':10})
            @event.listens_for(engine,'connect')
            def keys(connection,_):connection.execute('PRAGMA foreign_keys=ON')
            try:
                phase2=[table for table in database.Base.metadata.sorted_tables if table.name.startswith(('study_','focus_')) or table.name=='time_entries']
                # Produce an actual v6 schema from current declarative metadata.
                with patch.object(database,'engine',engine),patch.dict(MIGRATIONS,{k:v for k,v in MIGRATIONS.items() if k<=6},clear=True):database.migrate()
                with engine.begin() as db:
                    for table in reversed(phase2):table.drop(db)
                    db.exec_driver_sql("INSERT INTO users(id,email,password_hash,encrypted_api_key,allow_paid_models) VALUES(91,'kept@example.com','kept-hash','kept-key',0)")
                    db.exec_driver_sql("INSERT INTO conversations(id,user_id,title,created_at,updated_at) VALUES(92,91,'Kept chat','','')")
                    db.exec_driver_sql("INSERT INTO messages(id,conversation_id,role,content,attachment_data,created_at,status,active) VALUES(93,92,'user','Kept content','Kept bytes','','complete',1)")
                with engine.connect() as db:
                    original={name:db.exec_driver_sql(f'SELECT * FROM {name}').all() for name in ('users','conversations','messages')}
                def failure(*_):raise RuntimeError('phase2 migration interruption')
                with patch.object(database,'engine',engine),patch.dict(MIGRATIONS,{8:failure}):
                    with self.assertRaisesRegex(RuntimeError,'phase2 migration interruption'):database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),6)
                    self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE name='study_courses'")),0)
                    for name,rows in original.items():self.assertEqual(db.exec_driver_sql(f'SELECT * FROM {name}').all(),rows)
                with patch.object(database,'engine',engine):
                    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:database.migrate(),range(2)))
                    database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),max(MIGRATIONS))
                    for name,rows in original.items():self.assertEqual(db.exec_driver_sql(f'SELECT * FROM {name}').all(),rows)
                    self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                    self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
                    self.assertIn('UNIQUE INDEX',db.scalar(text("SELECT sql FROM sqlite_master WHERE name='ix_focus_one_active_owner'")))
                backups=list(Path(folder).glob('*.bak'));self.assertEqual(len(backups),2)
                for backup in backups:
                    self.assertEqual(backup.stat().st_mode&0o777,0o600)
                    with sqlite3.connect(backup) as db:
                        self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                        self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],6)
                        self.assertEqual(db.execute('SELECT attachment_data FROM messages').fetchone()[0],'Kept bytes')
            finally:engine.dispose()

    def test_intermediate_schema8_missing_segments_preserves_measured_history(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'intermediate8.db';engine=create_engine(f'sqlite:///{path}')
            try:
                with patch.object(database,'engine',engine):database.migrate()
                with engine.begin() as db:
                    db.exec_driver_sql('DELETE FROM schema_migrations WHERE version=9')
                    for table,columns in [('focus_sessions',['segments']),('time_entries',['segments','adjusted','allocation_estimated'])]:
                        for column in columns:db.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN {column}')
                    db.exec_driver_sql("INSERT INTO users(id,email,password_hash,allow_paid_models) VALUES(1,'preserved@example.com','original',0)")
                    db.exec_driver_sql("INSERT INTO focus_sessions(id,owner_id,kind,status,planned_seconds,elapsed_seconds,started_at,ended_at,notes,revision) VALUES(1,1,'tracking','stopped',NULL,600,'2026-10-10T23:55:00+00:00','2026-10-11T00:20:00+00:00','original note',1)")
                    db.exec_driver_sql("INSERT INTO time_entries(id,owner_id,session_id,started_at,ended_at,duration_seconds,notes,revision) VALUES(1,1,1,'2026-10-10T23:55:00+00:00','2026-10-11T00:20:00+00:00',600,'original note',1)")
                with patch.object(database,'engine',engine):database.migrate();database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),max(MIGRATIONS))
                    row=db.exec_driver_sql('SELECT duration_seconds,notes,segments,allocation_estimated FROM time_entries').one()
                    self.assertEqual(tuple(row),(600,'original note','[]',1))
                    self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
                self.assertEqual(len(list(Path(folder).glob('*.bak'))),1)
            finally:engine.dispose()
