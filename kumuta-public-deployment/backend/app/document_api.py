"""Private local file APIs; ownership checked before every operation."""
import hashlib
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import User, Conversation, Message, Attachment
from .workspace_models import Task, TaskDocument, Project
from .document_models import Document, DocumentChunk, StoredFile
from .dataset_models import Dataset
from . import documents as service, workspaces


class Revision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)


class ConfirmDelete(Revision):
    confirmation: Literal['DELETE']

class AttachmentSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attachment_id: int | None = Field(default=None, gt=0)


def register(app, user_dependency, db_dependency):
    @app.post('/conversations/{cid}/attachments/{mid}/library', status_code=201)
    async def import_attachment(cid: int, mid: int, data: AttachmentSource,
                                user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        import base64
        import io
        conversation = db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id))
        if conversation is None: raise HTTPException(404, 'Conversation not found')
        if conversation.project_id is None: raise HTTPException(422, 'Move this conversation to a project before saving its PDF to Documents.')
        workspaces.owned_project(conversation.project_id, user, db, writable=True)
        message = db.scalar(select(Message).where(Message.id == mid, Message.conversation_id == cid))
        if message is None: raise HTTPException(404, 'Attachment not found')
        source = db.scalar(select(Attachment).where(Attachment.id == data.attachment_id, Attachment.message_id == mid)) if data.attachment_id else message
        if source is None or not source.attachment_data: raise HTTPException(404, 'Attachment not found')
        if source.attachment_mime != 'application/pdf': raise HTTPException(415, 'Only PDFs can be imported into the searchable document library. Images remain in chat attachments.')
        if len(source.attachment_data) > (service.MAX_FILE * 4 // 3 + 8): raise HTTPException(413, 'PDF source exceeds the 8 MB document limit.')
        try: content = base64.b64decode(source.attachment_data, validate=True)
        except ValueError: raise HTTPException(422, 'Stored attachment is invalid.') from None
        # Reuse upload validation/quota/dedup/extraction. No browser re-upload or provider call.
        return await upload(file=UploadFile(filename=source.attachment_name, file=io.BytesIO(content)),
                            project_id=conversation.project_id, conversation_id=None, user=user, db=db)

    @app.post('/documents', status_code=201)
    async def upload(file: UploadFile = File(...), project_id: Optional[int] = Form(None), conversation_id: Optional[int] = Form(None),
                     user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.keys_for(user, db, project_id, conversation_id)
        filename = Path((file.filename or 'upload').replace('\\', '/')).name
        filename = ''.join(c for c in filename if ord(c) >= 32)[:255]
        mime = service.MIMES.get(Path(filename).suffix.lower())
        if not mime:
            raise HTTPException(415, 'Upload PDF, DOCX, UTF-8 TXT or Markdown. Images still use chat attachments.')
        data = await file.read(service.MAX_FILE + 1)
        await file.close()
        if not data or len(data) > service.MAX_FILE:
            raise HTTPException(413, 'Upload a non-empty document up to 8 MB.')
        if mime == 'application/pdf' and not data.startswith(b'%PDF-'):
            raise HTTPException(422, 'Invalid PDF signature.')
        if filename.lower().endswith('.docx') and not data.startswith(b'PK\x03\x04'):
            raise HTTPException(422, 'Invalid DOCX signature.')
        if mime.startswith('text/'):
            try: value = data.decode('utf-8-sig')
            except UnicodeDecodeError: raise HTTPException(422, 'Text documents must use UTF-8 encoding.') from None
            if '\x00' in value or any(ord(c) < 32 and c not in '\n\r\t\f' for c in value):
                raise HTTPException(422, 'Binary content is not a text document.')
        workspaces.lock_writes(user, db)
        keys = service.keys_for(user, db, project_id, conversation_id)
        if project_id is not None:
            workspaces.owned_project(project_id, user, db, writable=True)
        key = f'project:{project_id}' if project_id is not None else f'conversation:{conversation_id}'
        digest = hashlib.sha256(data).hexdigest()
        existing = db.scalar(select(Document).where(Document.user_id == user.id, Document.scope_key.in_(keys), Document.sha256 == digest))
        if existing:
            return {**service.view(existing), 'duplicate': True}
        count, size = db.execute(select(func.count(), func.coalesce(func.sum(Document.size), 0)).where(Document.user_id == user.id)).one()
        dataset_size = db.scalar(select(func.coalesce(func.sum(Dataset.size), 0)).where(Dataset.owner_id == user.id))
        if count >= 1000 or size + dataset_size + len(data) > service.MAX_OWNER_BYTES:
            raise HTTPException(413, 'Document storage limit reached (1000 files / 250 MB). Delete unused files first.')
        if db.scalar(select(func.count()).select_from(Document).where(Document.user_id == user.id, Document.status.in_(['queued', 'processing']))) >= 20:
            raise HTTPException(429, 'At most 20 queued/processing files per user. Wait before uploading more.')
        stored = service.store(data, filename)
        try:
            ledger = StoredFile(storage_key=stored)
            db.add(ledger); db.flush()
            row = Document(user_id=user.id, project_id=project_id, conversation_id=conversation_id, scope_key=key,
                           file_id=ledger.id, filename=filename, mime=mime, size=len(data), sha256=digest)
            db.add(row); db.commit()
        except BaseException:
            db.rollback()
            service.storage_path(stored).unlink(missing_ok=True)
            raise
        service.notify_worker()
        return {**service.view(row), 'duplicate': False}

    @app.get('/documents')
    def listing(project_id: Optional[int] = None, conversation_id: Optional[int] = None, q: str = Query('', max_length=200),
                status: Optional[Literal['queued', 'processing', 'ready', 'error']] = None,
                file_type: Optional[Literal['pdf', 'docx', 'text']] = None,
                limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        keys = service.keys_for(user, db, project_id, conversation_id)
        query = select(Document).where(Document.user_id == user.id, Document.scope_key.in_(keys))
        if conversation_id is not None:
            from .boards import conversation_document_ids
            board_ids = conversation_document_ids(conversation_id, user, db)
            if board_ids is not None: query = query.where(Document.id.in_(board_ids))
        if q.strip(): query = query.where(Document.filename.icontains(q.strip(), autoescape=True))
        if status: query = query.where(Document.status == status)
        if file_type:
            mimes = {'pdf': ['application/pdf'], 'docx': [service.MIMES['.docx']], 'text': ['text/plain', 'text/markdown']}
            query = query.where(Document.mime.in_(mimes[file_type]))
        rows = list(db.scalars(query.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(limit+1)))
        page = rows[:limit]
        conversation_projects = dict(db.execute(select(Conversation.id, Conversation.project_id).where(Conversation.id.in_([r.conversation_id for r in page if r.conversation_id]))).all())
        document_projects = {r.id: r.project_id or conversation_projects.get(r.conversation_id) for r in page}
        refs = {}
        for did, task in db.execute(select(TaskDocument.document_id, Task).join(Task, Task.id == TaskDocument.task_id).join(Project, Project.id == Task.project_id).where(TaskDocument.document_id.in_(document_projects), Project.owner_id == user.id)):
            if document_projects[did] == task.project_id:
                refs.setdefault(did, []).append({'id': task.id, 'title': task.title})
        return {'items': [{**service.view(r), 'task_refs': refs.get(r.id, [])} for r in page], 'has_more': len(rows) > limit}

    @app.get('/documents/search')
    def search(q: str = Query(..., min_length=1, max_length=300), project_id: Optional[int] = None, conversation_id: Optional[int] = None,
               limit: int = Query(12, ge=1, le=30), user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        keys = service.keys_for(user, db, project_id, conversation_id)
        from .boards import conversation_document_ids
        board_ids = conversation_document_ids(conversation_id, user, db) if conversation_id is not None else None
        return {'items': service.search(user, keys, q, db, ids=board_ids, limit=limit), 'ai_calls': 0}

    @app.get('/documents/{did}')
    def detail(did: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        return service.view(service.owned(did, user, db))

    @app.get('/documents/{did}/file')
    def download(did: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        row = service.owned(did, user, db)
        path = service.storage_path(db.get(StoredFile, row.file_id).storage_key)
        if not path.is_file(): raise HTTPException(404, 'Stored file unavailable')
        return FileResponse(path, media_type=row.mime, filename=row.filename, content_disposition_type='attachment',
            headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.get('/documents/{did}/chunks')
    def preview(did: int, page: Optional[int] = Query(None, ge=1), chunk_id: Optional[int] = None,
                limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
                user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        document = service.owned(did, user, db)
        query = select(DocumentChunk).where(DocumentChunk.document_id == did)
        if page is not None: query = query.where(DocumentChunk.page == page)
        if chunk_id is not None: query = query.where(DocumentChunk.id == chunk_id)
        chunks = list(db.scalars(query.order_by(DocumentChunk.ordinal).offset(offset).limit(limit+1)))
        return {'document': service.view(document), 'items': [service.passage(c, document) for c in chunks[:limit]], 'has_more': len(chunks) > limit}

    @app.post('/documents/{did}/retry')
    def retry(did: int, data: Revision, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(did, user, db)
        workspaces.check_revision(row, data.revision)
        if row.project_id is not None: workspaces.owned_project(row.project_id, user, db, writable=True)
        if row.status != 'error': raise HTTPException(409, 'Only failed documents can be retried.')
        if row.attempts >= 5: raise HTTPException(409, 'Retry limit reached. Export a simpler file, then upload it again.')
        row.status, row.error = 'queued', None
        workspaces.touch(row)
        db.commit()
        service.notify_worker()
        return service.view(row)

    @app.delete('/documents/{did}')
    def remove(did: int, data: ConfirmDelete, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(did, user, db)
        workspaces.check_revision(row, data.revision)
        db.delete(row); db.commit()
        service.cleanup_files()
        return {'ok': True}
