"""Real v9 upgrade preserves unknown historical dates, rollback and backups."""
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_api
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from app import database, migrations
from app.workspace_models import Workspace, Project, TaskColumn, Task
from app.study_models import Course, Chapter, Lesson


class AnalyticsMigrationTests(unittest.TestCase):
    def test_v9_populated_upgrade_rollback_retry_and_retention(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'upgrade.db';engine=create_engine(f'sqlite:///{path}',connect_args={'check_same_thread':False,'timeout':10})
            try:
                with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{k:v for k,v in migrations.MIGRATIONS.items() if k<=9},clear=True):database.migrate()
                with Session(engine) as db:
                    user=database.User(email='legacy@test.com',password_hash='kept');db.add(user);db.flush()
                    workspace=Workspace(owner_id=user.id,name='Legacy');db.add(workspace);db.flush()
                    project=Project(owner_id=user.id,workspace_id=workspace.id,name='Legacy');db.add(project);db.flush()
                    column=TaskColumn(project_id=project.id,name='Done',position=1024,is_done=True);db.add(column);db.flush()
                    course=Course(owner_id=user.id,project_id=project.id,title='Legacy');db.add(course);db.flush()
                    chapter=Chapter(owner_id=user.id,project_id=project.id,course_id=course.id,title='Legacy');db.add(chapter);db.flush()
                    db.add(Task(project_id=project.id,column_id=column.id,created_by=user.id,title='Retained task',completed=True,position=1024))
                    db.add(Lesson(owner_id=user.id,project_id=project.id,course_id=course.id,chapter_id=chapter.id,title='Retained lesson',content='Kept bytes',completed=True))
                    db.commit()
                with engine.begin() as db:
                    for table in ('tasks','study_lessons'):db.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN completed_at')
                original=migrations.MIGRATIONS[10]
                def fail(connection,timestamp):original(connection,timestamp);raise RuntimeError('Interrupted analytics upgrade')
                with patch.object(database,'engine',engine),patch.dict(migrations.MIGRATIONS,{10:fail}):
                    with self.assertRaisesRegex(RuntimeError,'Interrupted'):database.migrate()
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),9)
                    self.assertNotIn('completed_at',{c['name'] for c in inspect(db).get_columns('tasks')})
                with patch.object(database,'engine',engine):
                    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:database.migrate(),range(2)))
                    database.migrate()
                with engine.begin() as db:
                    self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),max(migrations.MIGRATIONS))
                    for table in ('tasks','study_lessons'):
                        self.assertIsNone(db.scalar(text(f'SELECT completed_at FROM {table}')))
                        db.exec_driver_sql(f'UPDATE {table} SET completed=0')
                        db.exec_driver_sql(f'UPDATE {table} SET completed=1')
                        self.assertIsNotNone(db.scalar(text(f'SELECT completed_at FROM {table}')))
                    self.assertEqual(db.scalar(text('SELECT content FROM study_lessons')),'Kept bytes')
                    self.assertEqual(db.exec_driver_sql('PRAGMA integrity_check').scalar(),'ok')
                    self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
                backups=list(Path(folder).glob('*.bak'));self.assertEqual(len(backups),2)
                for backup in backups:
                    self.assertEqual(backup.stat().st_mode&0o777,0o600)
                    with sqlite3.connect(backup) as db:
                        self.assertEqual(db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],9)
                        self.assertEqual(db.execute('SELECT content FROM study_lessons').fetchone()[0],'Kept bytes')
            finally:engine.dispose()
