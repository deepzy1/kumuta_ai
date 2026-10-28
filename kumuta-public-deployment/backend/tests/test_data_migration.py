"""Populated v10 -> v11 upgrade, private backup, rollback/retry and concurrency."""
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import unittest
from unittest.mock import patch
import test_api
from sqlalchemy import create_engine, text
from app import database, migrations


class DataMigrationTests(unittest.TestCase):
    def test_populated_v10_upgrade(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'upgrade.db'
            engine=create_engine(f'sqlite:///{path}',connect_args={'check_same_thread':False,'timeout':15})
            try:
                with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=10},clear=True):database.migrate()
                with engine.begin() as db:
                    db.exec_driver_sql("INSERT INTO users (email,password_hash,allow_paid_models) VALUES ('legacy@example.com','original hash',0)")
                    db.exec_driver_sql("INSERT INTO conversations (user_id,title,created_at,updated_at) VALUES (1,'Retained chat','','')")
                    db.exec_driver_sql("INSERT INTO messages (conversation_id,role,content,status,active,created_at) VALUES (1,'user','Retained content','complete',1,'')")
                    db.exec_driver_sql('DROP TABLE data_reports')
                    db.exec_driver_sql('DROP TABLE datasets')
                original=migrations.MIGRATIONS[11]
                def fail(c,t):original(c,t);raise RuntimeError('Interrupted upgrade')
                with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{11:fail}):
                    with self.assertRaisesRegex(RuntimeError,'Interrupted'):database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),10)
                    self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE name='datasets'")),0)
                with patch.object(database,'engine',engine):
                    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:database.migrate(),range(2)))
                    database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),max(migrations.MIGRATIONS))
                    self.assertEqual(db.scalar(text('SELECT password_hash FROM users')),'original hash')
                    self.assertEqual(db.scalar(text('SELECT content FROM messages')),'Retained content')
                    self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                    self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
                backups=list(Path(folder).glob('*.bak'));self.assertEqual(len(backups),2)
                for backup in backups:
                    self.assertEqual(backup.stat().st_mode&0o777,0o600)
                    with sqlite3.connect(backup) as db:self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],10)
            finally:engine.dispose()

    def test_populated_v11_report_upgrade_rollback_and_dataset_retention(self):
        from sqlalchemy.orm import Session
        from app.workspace_models import Workspace, Project
        from app.dataset_models import Dataset
        from app.document_models import StoredFile
        with TemporaryDirectory() as folder:
            path=Path(folder)/'v11.db';engine=create_engine(f'sqlite:///{path}')
            try:
                with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=11},clear=True):database.migrate()
                with Session(engine) as db:
                    user=database.User(email='v11@test.com',password_hash='kept');db.add(user);db.flush()
                    ws=Workspace(owner_id=user.id,name='Preserved');db.add(ws);db.flush()
                    project=Project(owner_id=user.id,workspace_id=ws.id,name='Preserved');db.add(project);db.flush()
                    stored=StoredFile(storage_key='a'*32);db.add(stored);db.flush()
                    db.add(Dataset(owner_id=user.id,project_id=project.id,file_id=stored.id,name='Preserved dataset',filename='data.csv',format='csv',size=100,sha256='b'*64,status='ready',metadata_json='[]'));db.commit()
                with engine.begin() as db:db.exec_driver_sql('DROP TABLE data_reports')
                original=migrations.MIGRATIONS[12]
                def fail(c,t):original(c,t);raise RuntimeError('Report upgrade interruption')
                with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{12:fail}):
                    with self.assertRaisesRegex(RuntimeError,'interruption'):database.migrate()
                with engine.connect() as db:self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),11)
                with patch.object(database,'engine',engine):database.migrate();database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),max(migrations.MIGRATIONS))
                    self.assertEqual(db.scalar(text('SELECT name FROM datasets')),'Preserved dataset')
                    self.assertEqual(db.scalar(text('SELECT storage_key FROM document_files')),'a'*32)
                    self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                    self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
                for backup in Path(folder).glob('*.bak'):
                    self.assertEqual(backup.stat().st_mode&0o777,0o600)
                    with sqlite3.connect(backup) as db:self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],11)
            finally:engine.dispose()
