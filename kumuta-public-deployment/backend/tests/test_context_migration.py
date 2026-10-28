"""Preserve intermediate live-reload data while making context IDs immutable."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_api as fixture
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from app import database, memory
from app.database import Conversation, User
from app.document_models import Document, DocumentChunk, StoredFile
from app.memory_models import Memory
from app.migrations import MIGRATIONS


class ContextMigrationTests(unittest.TestCase):
    def test_v5_intermediate_schema_preserves_rows_indexes_and_never_reuses_ids(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'intermediate.db'
            engine = create_engine(f'sqlite:///{path}')
            @event.listens_for(engine, 'connect')
            def foreign_keys(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
            tables = [Memory.__table__, Document.__table__, DocumentChunk.__table__]
            try:
                for table in tables:
                    table.dialect_options['sqlite']['autoincrement'] = False
                with patch.object(database, 'engine', engine), patch.dict(MIGRATIONS,
                    {k: v for k, v in MIGRATIONS.items() if k < 6}, clear=True):
                    database.migrate()
            finally:
                for table in tables:
                    table.dialect_options['sqlite']['autoincrement'] = True
            try:
                with Session(engine) as db:
                    db.add(User(id=41, email='intermediate@example.com', password_hash='retained-hash')); db.flush()
                    db.add(Conversation(id=51, user_id=41, title='Retained chat')); db.flush()
                    db.add(StoredFile(id=61, storage_key='a' * 32)); db.flush()
                    db.add(Document(id=8, user_id=41, conversation_id=51, scope_key='conversation:51', file_id=61,
                        filename='retained.txt', mime='text/plain', size=10, sha256='b' * 64, status='ready'))
                    db.add(Memory(id=7, user_id=41, scope='global', scope_key='global', content='Retained preference',
                        fingerprint=memory.fingerprint('Retained preference'))); db.flush()
                    db.add(DocumentChunk(id=9, document_id=8, ordinal=0, page=1, section='Retained', content='Retained evidence'))
                    db.commit()
                original_upgrade = MIGRATIONS[6]
                def fail_after_copy(connection, timestamp):
                    original_upgrade(connection, timestamp)
                    raise RuntimeError('Simulated interruption after table replacement')
                with patch.object(database, 'engine', engine), patch.dict(MIGRATIONS, {6: fail_after_copy}):
                    with self.assertRaisesRegex(RuntimeError, 'Simulated interruption'):
                        database.migrate()
                with engine.connect() as db:
                    self.assertNotIn('AUTOINCREMENT', db.scalar(text("SELECT sql FROM sqlite_master WHERE name='documents'")))
                    self.assertEqual(db.scalar(text('SELECT content FROM document_chunks WHERE id=9')), 'Retained evidence')
                    self.assertEqual(db.execute(text('PRAGMA foreign_key_check')).all(), [])
                with patch.object(database, 'engine', engine):
                    database.migrate()
                    database.migrate()
                with Session(engine) as db:
                    self.assertEqual(db.get(User, 41).password_hash, 'retained-hash')
                    self.assertEqual(db.get(Memory, 7).content, 'Retained preference')
                    self.assertEqual(db.get(Document, 8).filename, 'retained.txt')
                    self.assertEqual(db.get(DocumentChunk, 9).content, 'Retained evidence')
                    self.assertEqual(db.scalar(text("SELECT count(*) FROM memory_fts WHERE memory_fts MATCH 'Retained'")), 1)
                    self.assertEqual(db.scalar(text("SELECT count(*) FROM document_fts WHERE document_fts MATCH 'Retained'")), 1)
                    self.assertEqual(db.execute(text('PRAGMA foreign_key_check')).all(), [])
                    for name in ('memories', 'documents', 'document_chunks'):
                        self.assertIn('AUTOINCREMENT', db.scalar(text('SELECT sql FROM sqlite_master WHERE name=:name'), {'name': name}))
                    db.delete(db.get(Document, 8)); db.delete(db.get(Memory, 7)); db.commit()
                    self.assertIsNone(db.get(DocumentChunk, 9))
                    replacement = Document(user_id=41, conversation_id=51, scope_key='conversation:51', file_id=61,
                        filename='new.txt', mime='text/plain', size=10, sha256='c' * 64)
                    fact = Memory(user_id=41, scope='global', scope_key='global', content='New preference', fingerprint='d' * 64)
                    db.add_all([replacement, fact]); db.flush()
                    chunk = DocumentChunk(document_id=replacement.id, ordinal=0, section='New', content='New evidence')
                    db.add(chunk); db.commit()
                    self.assertGreater(replacement.id, 8); self.assertGreater(fact.id, 7); self.assertGreater(chunk.id, 9)
                    self.assertEqual(db.scalar(text('SELECT count(*) FROM document_fts')), 1)
                backups = list(Path(directory).glob('*.bak'))
                self.assertEqual(len(backups), 2)
                for backup in backups:
                    with sqlite3.connect(backup) as old:
                        self.assertEqual(old.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                        self.assertEqual(old.execute('SELECT content FROM document_chunks WHERE id=9').fetchone()[0], 'Retained evidence')
                        self.assertEqual(old.execute('SELECT max(version) FROM schema_migrations').fetchone()[0], 5)
            finally:
                engine.dispose()
