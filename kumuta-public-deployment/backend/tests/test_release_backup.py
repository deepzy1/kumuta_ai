"""D7-9 backup/restore checks with synthetic populated SQLite and private files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest

SPEC = importlib.util.spec_from_file_location('backup_release', Path(__file__).resolve().parents[2]/'scripts/backup_release.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BackupRestoreTests(unittest.TestCase):
    def test_populated_backup_restore_hashes_and_permissions(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); database=root/'source.db';storage=root/'source-files';storage.mkdir()
            (storage/'synthetic-file').write_bytes(b'Synthetic private source bytes')
            with sqlite3.connect(database) as db:
                db.executescript('PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; CREATE TABLE owners(id INTEGER PRIMARY KEY); CREATE TABLE sources(id INTEGER PRIMARY KEY,owner_id INTEGER REFERENCES owners(id)); INSERT INTO owners VALUES(1); INSERT INTO sources VALUES(2,1);')
                db.commit()
                snapshot=root/'snapshot';MODULE.backup(database,storage,snapshot)
            hashes=json.loads((snapshot/'manifest.json').read_text())['files']
            for key,digest in hashes.items():
                path=snapshot/key
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
                self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual((snapshot/'documents').stat().st_mode&0o777,0o700)
            restored=root/'restored';shutil.copytree(snapshot,restored)
            with sqlite3.connect(restored/'chat.db') as db:
                self.assertEqual(db.execute('SELECT * FROM sources').fetchall(),[(2,1)])
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual((restored/'documents/synthetic-file').read_bytes(),(storage/'synthetic-file').read_bytes())
            with self.assertRaises(ValueError):MODULE.backup(database,storage,snapshot)

    def test_unsafe_target_and_symlink_rejected_before_copy(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);database=root/'source.db';database.touch();storage=root/'files';storage.mkdir()
            with self.assertRaises(ValueError):MODULE.backup(database,storage,storage/'snapshot')
            (storage/'outside').symlink_to(root/'source.db')
            with self.assertRaises(ValueError):MODULE.backup(database,storage,root/'snapshot')
            self.assertFalse((root/'snapshot').exists())
