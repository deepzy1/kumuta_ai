"""Dataset queue and private source access reuse the document storage ledger."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import threading
from fastapi import HTTPException
from sqlalchemy import select, text, update
from .database import SessionLocal, now
from .dataset_models import Dataset
from .document_models import StoredFile
from . import documents, workspaces
from .dataset_parse import MAX_FILE, MAX_ROWS, MAX_COLUMNS, MAX_CELLS


_parser_slots = threading.BoundedSemaphore(2)

def owned(pid, did, user, db, writable=False):
    workspaces.owned_project(pid, user, db, writable=writable)
    row = db.scalar(select(Dataset).where(Dataset.id == did, Dataset.owner_id == user.id, Dataset.project_id == pid))
    if row is None: raise HTTPException(404, 'Dataset not found in this project')
    return row


def view(row):
    sheets = json.loads(row.metadata_json)
    return {**workspaces.fields(row, 'id project_id name filename format size sha256 status error attempts revision created_at updated_at'),
            'sheets': sheets, 'row_count': sum(s['row_count'] for s in sheets),
            'column_count': sum(s['column_count'] for s in sheets), 'ai_calls': 0}


def read_source(key, format, digest):
    if not _parser_slots.acquire(timeout=2): raise HTTPException(429, 'Dataset parser is busy. Retry shortly.')
    try: return _read_source(key, format, digest)
    finally: _parser_slots.release()


def _read_source(key, format, digest):
    path = documents.storage_path(key)
    try:
        with path.open('rb') as source: data = source.read(MAX_FILE + 1)
        if len(data) > MAX_FILE or hashlib.sha256(data).hexdigest() != digest: raise HTTPException(409, 'Dataset source changed or is corrupt. Upload it again.')
        # Minimal environment excludes credentials; all paths/arguments are server-owned.
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG') or k.startswith('DATASET_MAX_')}
        child = subprocess.run([sys.executable, str(Path(__file__).with_name('dataset_parse.py')), str(path), format],
                               capture_output=True, timeout=20, env=env)
        if len(child.stdout) > 24 * 1024 * 1024: raise HTTPException(422, 'Dataset parser output limit exceeded.')
        result = json.loads(child.stdout)
        if child.returncode or 'error' in result: raise HTTPException(422, result.get('error', 'Dataset parser failed safely.'))
        return result['sheets']
    except HTTPException: raise
    except FileNotFoundError: raise HTTPException(409, 'Dataset source unavailable. Upload it again.') from None
    except (subprocess.TimeoutExpired, ValueError, OSError): raise HTTPException(422, 'Dataset processing failed or exceeded its 20-second limit. Export a smaller file.') from None


def sheet_data(row, sheet, db):
    if row.status != 'ready': raise HTTPException(409, row.error or 'Dataset is still processing.')
    stored = db.get(StoredFile, row.file_id)
    key, format, digest = stored.storage_key, row.format, row.sha256
    result = read_source(key, format, digest)
    if sheet is None: return result[0]
    found = next((s for s in result if s['name'] == sheet), None)
    if found is None: raise HTTPException(422, 'Worksheet not found.')
    return found


def process_next():
    with SessionLocal() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        db.execute(update(Dataset).where(Dataset.status == 'processing', Dataset.started_at < cutoff).values(
            status='error', error='Processing was interrupted. Retry this dataset.', job_token=None, started_at=None))
        row = db.scalar(select(Dataset).where(Dataset.status == 'queued').order_by(Dataset.id).limit(1))
        if row is None: db.commit(); return False
        token = uuid.uuid4().hex
        row.status, row.started_at, row.job_token = 'processing', now(), token
        row.attempts += 1
        did, key, format, digest = row.id, db.get(StoredFile, row.file_id).storage_key, row.format, row.sha256
        db.commit()
    try:
        result = read_source(key, format, digest)
        metadata = [{k: v for k, v in s.items() if k != 'rows'} for s in result]
        status, error = 'ready', None
    except HTTPException as exc:
        metadata, status, error = [], 'error', str(exc.detail)[:300]
    with SessionLocal() as db:
        db.execute(update(Dataset).where(Dataset.id == did, Dataset.job_token == token).values(
            status=status, error=error, metadata_json=json.dumps(metadata), job_token=None, started_at=None, updated_at=now(), revision=Dataset.revision+1))
        db.commit()
    return True


async def worker(stop):
    while not stop.is_set():
        try:
            more = await asyncio.to_thread(process_next)
            if more: continue
        except Exception:
            import logging
            logging.getLogger('kumuta').warning('Dataset worker failed; retrying next tick.')
        try: await asyncio.wait_for(stop.wait(), timeout=1)
        except asyncio.TimeoutError: pass
