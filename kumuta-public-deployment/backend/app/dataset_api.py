"""Project-scoped datasets. No provider imports or calls."""
import hashlib
from pathlib import Path
from typing import Literal
from fastapi import Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .database import User
from .dataset_models import Dataset
from .document_models import Document, StoredFile
from . import datasets as service, documents, workspaces


class Revision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)


class Rename(Revision):
    name: str = Field(min_length=1, max_length=200)
    @field_validator('name')
    @classmethod
    def clean(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value): raise ValueError('Use a nonblank name without control characters.')
        return value.strip()


class ConfirmDelete(Revision):
    confirmation: Literal['DELETE']


def upload_dataset(file, user, db, *, project_id=None, board=None, conversation_id=None):
    """One validator, quota, dedup, storage and queue path for project/board files."""
    pid=project_id
    board_id=board.id if board is not None else None
    def authorize():
        if board_id is not None:
            from . import boards
            boards.owned(board_id,user,db,writable=True)
        elif conversation_id is not None:
            from .chat_sources import conversation_owned
            conversation_owned(conversation_id,user,db,writable=True)
        else:
            workspaces.owned_project(pid,user,db,writable=True)
    authorize()
    filename = Path((file.filename or 'dataset').replace('\\', '/')).name
    filename = ''.join(c for c in filename if ord(c) >= 32)[:255]
    format = Path(filename).suffix.lower().lstrip('.')
    if format not in ('csv', 'xlsx'): raise HTTPException(415, 'Upload a CSV or XLSX dataset.')
    try: data = file.file.read(service.MAX_FILE + 1)
    finally: file.file.close()
    if not data or len(data) > service.MAX_FILE: raise HTTPException(413, f'Upload a nonempty dataset up to {service.MAX_FILE // 1024 // 1024} MB.')
    if format == 'xlsx' and not data.startswith(b'PK\x03\x04'): raise HTTPException(422, 'Invalid, encrypted or unsupported XLSX file.')
    digest = hashlib.sha256(data).hexdigest()
    workspaces.lock_writes(user, db)
    authorize()
    existing = db.scalar(select(Dataset).where(Dataset.owner_id == user.id, Dataset.project_id == pid, Dataset.board_id == board_id, Dataset.conversation_id == conversation_id, Dataset.sha256 == digest))
    if existing: return {**service.view(existing), 'duplicate': True}
    count, size = db.execute(select(func.count(), func.coalesce(func.sum(Dataset.size), 0)).where(Dataset.owner_id == user.id)).one()
    doc_size = db.scalar(select(func.coalesce(func.sum(Document.size), 0)).where(Document.user_id == user.id))
    if count >= 100 or size + doc_size + len(data) > documents.MAX_OWNER_BYTES: raise HTTPException(413, 'Dataset limit reached (100 datasets / 250 MB shared private file quota).')
    if db.scalar(select(func.count()).select_from(Dataset).where(Dataset.owner_id == user.id, Dataset.status.in_(['queued', 'processing']))) >= 5:
        raise HTTPException(429, 'Wait for pending datasets to finish (maximum 5).')
    key = documents.store(data, filename)
    try:
        stored = StoredFile(storage_key=key); db.add(stored); db.flush()
        row = Dataset(owner_id=user.id, project_id=pid, board_id=board_id, conversation_id=conversation_id, file_id=stored.id, name=filename[:200], filename=filename, format=format, size=len(data), sha256=digest)
        db.add(row); db.commit()
    except BaseException:
        db.rollback(); documents.storage_path(key).unlink(missing_ok=True); raise
    return {**service.view(row), 'duplicate': False}


def register(app, user_dependency, db_dependency):
    base = '/projects/{pid}/data'

    @app.get(base + '/overview')
    def overview(pid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.owned_project(pid, user, db)
        rows = list(db.scalars(select(Dataset).where(Dataset.owner_id == user.id, Dataset.project_id == pid).order_by(Dataset.id.desc())))
        from .report_models import DataReport
        from .data_reports import view as report_view
        recent_reports = list(db.scalars(select(DataReport).where(DataReport.owner_id == user.id, DataReport.project_id == pid).order_by(DataReport.updated_at.desc()).limit(6)))
        return {'datasets': len(rows), 'rows': sum(service.view(r)['row_count'] for r in rows),
                'columns': sum(service.view(r)['column_count'] for r in rows),
                'reports': db.scalar(select(func.count()).select_from(DataReport).where(DataReport.owner_id == user.id, DataReport.project_id == pid)),
                'recent_datasets': [service.view(r) for r in rows[:6]], 'recent_reports': [report_view(r) for r in recent_reports], 'ai_calls': 0}

    @app.post(base + '/datasets', status_code=201)
    def upload(pid: int, file: UploadFile = File(...), user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.owned_project(pid, user, db, writable=True)
        return upload_dataset(file,user,db,project_id=pid)

    @app.get(base + '/datasets')
    def listing(pid: int, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0, le=100000),
                user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.owned_project(pid, user, db)
        rows = list(db.scalars(select(Dataset).where(Dataset.owner_id == user.id, Dataset.project_id == pid).order_by(Dataset.id.desc()).offset(offset).limit(limit+1)))
        return {'items': [service.view(r) for r in rows[:limit]], 'has_more': len(rows) > limit, 'ai_calls': 0,
                'limits': {'file_bytes': service.MAX_FILE, 'rows': service.MAX_ROWS, 'columns': service.MAX_COLUMNS, 'cells': service.MAX_CELLS}}

    @app.get(base + '/datasets/{did}')
    def detail(pid: int, did: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        return service.view(service.owned(pid, did, user, db))

    @app.get(base + '/datasets/{did}/preview')
    def preview(pid: int, did: int, sheet: str | None = Query(None, max_length=120), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=50000),
                user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        row = service.owned(pid, did, user, db)
        data = service.sheet_data(row, sheet, db)
        return {**{k: v for k, v in data.items() if k != 'rows'}, 'items': data['rows'][offset:offset+limit],
                'offset': offset, 'has_more': offset + limit < len(data['rows']), 'ai_calls': 0}

    @app.get(base + '/datasets/{did}/schema')
    def schema(pid: int, did: int, sheet: str | None = Query(None, max_length=120), user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        row = service.owned(pid, did, user, db)
        # Verify the canonical source too, so changed/missing files never appear healthy.
        data = service.sheet_data(row, sheet, db)
        return {k: v for k, v in data.items() if k != 'rows'} | {'ai_calls': 0}

    @app.patch(base + '/datasets/{did}')
    def rename(pid: int, did: int, data: Rename, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(pid, did, user, db, writable=True); workspaces.check_revision(row, data.revision)
        row.name = data.name; workspaces.touch(row); db.commit()
        return service.view(row)

    @app.post(base + '/datasets/{did}/retry')
    def retry(pid: int, did: int, data: Revision, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(pid, did, user, db, writable=True); workspaces.check_revision(row, data.revision)
        if row.status != 'error' or row.attempts >= 3: raise HTTPException(409, 'Only failed datasets with fewer than three attempts can retry.')
        row.status, row.error = 'queued', None; workspaces.touch(row); db.commit()
        return service.view(row)

    @app.delete(base + '/datasets/{did}')
    def remove(pid: int, did: int, data: ConfirmDelete, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(pid, did, user, db); workspaces.check_revision(row, data.revision)
        db.delete(row); db.commit(); documents.cleanup_files()
        return {'ok': True, 'ai_calls': 0}
