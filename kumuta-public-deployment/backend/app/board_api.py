"""Authenticated backend-only Canvas foundation using shared dependencies."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import User, Conversation, now
from .board_models import Board, BoardConversation, BoardResourceLink, BoardSceneRevision
from . import board_schemas as schema, boards as service, workspaces


class BoundedBoardRoute(APIRoute):
    max_request_bytes = schema.MAX_REQUEST_BYTES
    max_request_error = 'Board request exceeds 8 MiB plus envelope allowance.'
    def get_route_handler(self):
        original = super().get_route_handler()

        async def bounded(request: Request):
            # Bound the actual stream, including chunked requests and dishonest
            # Content-Length, before FastAPI parses a potentially large body.
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > self.max_request_bytes:
                    raise HTTPException(413, self.max_request_error)
                body.extend(chunk)
            request._body = bytes(body)
            try: return await original(request)
            except RecursionError: raise HTTPException(422, 'JSON nesting is too deep.') from None

        return bounded


def register(app, user_dependency, db_dependency):
    router = APIRouter(prefix='/boards', route_class=BoundedBoardRoute)

    @router.post('', status_code=201)
    def create(data: schema.BoardCreate, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        workspaces.owned_workspace(data.workspace_id, user, db)
        if data.project_id is not None:
            project = workspaces.owned_project(data.project_id, user, db, writable=True)
            if project.workspace_id != data.workspace_id: raise HTTPException(404, 'Project not found in this workspace')
        if db.scalar(select(func.count()).select_from(Board).where(Board.owner_id == user.id)) >= 1000:
            raise HTTPException(413, 'Use at most 1000 boards per owner.')
        row = Board(owner_id=user.id, **data.model_dump())
        db.add(row); db.commit()
        return service.view(row,user,db)

    @router.get('')
    def listing(workspace_id: int, project_id: int | None = None, status: Literal['active','archived'] = 'active',
                limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000),
                user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.owned_workspace(workspace_id, user, db)
        query = select(Board).where(Board.owner_id == user.id, Board.workspace_id == workspace_id, Board.status == status)
        if project_id is not None:
            project = workspaces.owned_project(project_id, user, db)
            if project.workspace_id != workspace_id: raise HTTPException(404, 'Project not found in this workspace')
            query = query.where(Board.project_id == project_id)
        rows = list(db.scalars(query.order_by(Board.updated_at.desc(), Board.id.desc()).offset(offset).limit(limit+1)))
        return {'items': [service.view(service.owned(r.id, user, db)) for r in rows[:limit]], 'has_more': len(rows)>limit, 'ai_calls': 0}

    @router.get('/{bid}')
    def detail(bid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        return service.view(service.owned(bid, user, db),user,db)

    @router.patch('/{bid}')
    def edit(bid: int, data: schema.BoardEdit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(bid, user, db, owner_only=True)
        for key, value in data.model_dump(exclude_unset=True).items(): setattr(row, key, value)
        row.updated_at = now(); db.commit()
        return service.view(row,user,db)

    @router.get('/{bid}/scene')
    def load(bid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        board = service.owned(bid, user, db)
        if board.current_revision == 0:
            return {'board_id': bid, 'revision': 0, 'schema_version': 1, 'scene': schema.Scene(elements=[]).model_dump(), 'ai_calls': 0}
        return service.revision_view(db.get(BoardSceneRevision, (bid, board.current_revision)), scene=True)

    @router.put('/{bid}/scene')
    def save(bid: int, data: schema.SceneSave, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        board = service.owned(bid, user, db, writable=True)
        if board.current_revision and 'resources' not in data.scene.model_fields_set:
            current = db.get(BoardSceneRevision, (bid, board.current_revision))
            if current and json.loads(current.scene_json).get('resources'):
                raise HTTPException(422, 'Reload the current Canvas editor to preserve resource frames.')
        if 'artifacts' not in data.scene.model_fields_set and board.current_revision:
            current = db.get(BoardSceneRevision, (bid, board.current_revision))
            if current and json.loads(current.scene_json).get('artifacts'):
                raise HTTPException(422, 'This board contains widgets. Reload with the current Canvas editor before saving; widget definitions must be explicitly preserved.')
        from . import canvas_resources
        previous = db.get(BoardSceneRevision, (bid, board.current_revision)) if board.current_revision else None
        old_refs = {f['id']:f['reference'] for f in json.loads(previous.scene_json).get('resources',[])} if previous else {}
        for frame in data.scene.resources:
            if old_refs.get(frame.id) != frame.reference.model_dump():
                source = canvas_resources.source(board,frame.reference.kind,frame.reference.source_id,db)
                if canvas_resources.fingerprint(frame.reference.kind,source) != frame.reference.fingerprint:
                    raise HTTPException(409,'Resource changed. Refresh its preview before saving a new reference.')
        row = service.save(board, data.expected_revision, json.dumps(data.scene.model_dump(), ensure_ascii=False, allow_nan=False, separators=(',', ':')), db)
        db.commit(); return service.revision_view(row, scene=True)

    @router.get('/{bid}/revisions')
    def revisions(bid: int, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000),
                  user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.owned(bid, user, db)
        rows = list(db.scalars(select(BoardSceneRevision).where(BoardSceneRevision.board_id == bid)
                              .order_by(BoardSceneRevision.revision.desc()).offset(offset).limit(limit+1)))
        return {'items': [service.revision_view(r) for r in rows[:limit]], 'has_more': len(rows)>limit, 'ai_calls': 0}

    @router.get('/{bid}/revisions/{revision}')
    def revision(bid: int, revision: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.owned(bid, user, db)
        row = db.get(BoardSceneRevision, (bid, revision))
        if row is None: raise HTTPException(404, 'Scene revision not found')
        return service.revision_view(row, scene=True)

    @router.post('/{bid}/revisions/{revision}/restore')
    def restore(bid: int, revision: int, data: schema.ExpectedRevision, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        board = service.owned(bid, user, db, writable=True)
        source = db.get(BoardSceneRevision, (bid, revision))
        if source is None: raise HTTPException(404, 'Scene revision not found')
        row = service.save(board, data.expected_revision, source.scene_json, db, restored_from=revision)
        db.commit(); return service.revision_view(row, scene=True)

    @router.get('/{bid}/conversations')
    def conversations(bid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        board = service.owned(bid, user, db)
        if service.role(board,user,db)=='viewer': raise HTTPException(403,'Board conversations require editing permission.')
        ids = list(db.scalars(select(BoardConversation.conversation_id).where(BoardConversation.board_id == bid)))
        rows = [service.conversation_in_scope(board,cid,user,db) for cid in ids if db.get(Conversation,cid).user_id==user.id]
        return {'items': [{'conversation_id': row.id, 'title': row.title, 'created_at': row.created_at, 'updated_at': row.updated_at} for row in sorted(rows,key=lambda r:(r.updated_at,r.id),reverse=True)], 'ai_calls': 0}

    @router.post('/{bid}/conversations/new', status_code=201)
    def new_conversation(bid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user,db)
        board = service.owned(bid,user,db,writable=True)
        if db.scalar(select(func.count()).select_from(BoardConversation).where(BoardConversation.board_id==bid)) >= 100:
            raise HTTPException(413,'Use at most 100 conversations per board.')
        row = Conversation(user_id=user.id,project_id=board.project_id if board.owner_id==user.id else None,title='New chat')
        db.add(row); db.flush()
        db.add(BoardConversation(board_id=bid,conversation_id=row.id)); db.commit()
        return {'conversation_id':row.id,'title':row.title,'created_at':row.created_at,'updated_at':row.updated_at,'ai_calls':0}

    @router.post('/{bid}/conversations', status_code=201)
    def link_conversation(bid: int, data: schema.ConversationLink, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        board = service.owned(bid, user, db, writable=True)
        conversation = service.conversation_in_scope(board, data.conversation_id, user, db)
        if conversation.generation_id: raise HTTPException(409, 'Stop the generating conversation before linking it.')
        existing = db.scalar(select(BoardConversation).where(BoardConversation.conversation_id == conversation.id))
        if existing is not None and existing.board_id != bid: raise HTTPException(409, 'Conversation is already linked to another board.')
        if existing is None:
            if db.scalar(select(func.count()).select_from(BoardConversation).where(BoardConversation.board_id == bid)) >= 100:
                raise HTTPException(413, 'Use at most 100 conversations per board.')
            db.add(BoardConversation(board_id=bid, conversation_id=conversation.id)); db.commit()
        return {'board_id': bid, 'conversation_id': conversation.id, 'ai_calls': 0}

    @router.delete('/{bid}/conversations/{cid}')
    def unlink_conversation(bid: int, cid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        board = service.owned(bid, user, db, writable=True)
        row = db.get(BoardConversation, (bid, cid))
        if row is None: raise HTTPException(404, 'Board conversation not found')
        conversation = service.conversation_in_scope(board, cid, user, db)
        if conversation.generation_id: raise HTTPException(409, 'Stop the generating conversation before unlinking it.')
        # Unlinking a conversation also revokes its board-specific document links.
        from .document_models import Document
        for link in db.scalars(select(BoardResourceLink).join(Document, Document.id == BoardResourceLink.document_id)
                               .where(BoardResourceLink.board_id == bid, Document.conversation_id == cid)):
            db.delete(link)
        db.delete(row); db.commit(); return {'ok': True, 'ai_calls': 0}

    @router.get('/{bid}/resources')
    def resources(bid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        board = service.owned(bid, user, db, owner_only=True)
        return {'items': [{'document_id': row.id, 'filename': row.filename, 'status': row.status} for row in service.resource_documents(board, user, db)], 'ai_calls': 0}

    @router.post('/{bid}/resources', status_code=201)
    def link_resource(bid: int, data: schema.ResourceLink, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        board = service.owned(bid, user, db, writable=True, owner_only=True)
        source = service.document_in_scope(board, data.document_id, user, db)
        if db.get(BoardResourceLink, (bid, source.id)) is None:
            from .canvas_resources import count_links
            if count_links(board,db) >= 100:
                raise HTTPException(413, 'Use at most 100 document links per board.')
            db.add(BoardResourceLink(board_id=bid, document_id=source.id)); db.commit()
        return {'board_id': bid, 'document_id': source.id, 'ai_calls': 0}

    @router.delete('/{bid}/resources/{did}')
    def unlink_resource(bid: int, did: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        service.owned(bid, user, db, writable=True, owner_only=True)
        row = db.get(BoardResourceLink, (bid, did))
        if row is None: raise HTTPException(404, 'Board resource not found')
        db.delete(row); db.commit(); return {'ok': True, 'ai_calls': 0}

    app.include_router(router)
