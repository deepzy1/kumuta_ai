"""Board authorization and atomic local persistence. No provider dependencies."""
import json

from fastapi import HTTPException
from sqlalchemy import LargeBinary, func, select, update

from .database import Conversation, now
from .document_models import Document
from .board_models import Board, BoardConversation, BoardResourceLink, BoardSceneRevision, BoardMember
from . import workspaces

MAX_OWNER_SCENE_BYTES = 250 * 1024 * 1024
MAX_REVISIONS = 500


def role(board, user, db):
    if board.owner_id == user.id: return 'owner'
    member = db.get(BoardMember, (board.id, user.id))
    return member.role if member and member.status == 'accepted' else None


def owned(bid, user, db, *, writable=False, owner_only=False):
    """Central board policy. Membership grants board content only, never sources."""
    board = db.get(Board, bid)
    if board is None: raise HTTPException(404, 'Board not found')
    access = role(board, user, db)
    if access is None: raise HTTPException(404, 'Board not found or access revoked')
    if owner_only and access != 'owner': raise HTTPException(403, 'Only the owner can manage this board or its private sources.')
    if writable and access == 'viewer': raise HTTPException(403, 'This board is view only.')
    if access == 'owner': workspaces.owned_workspace(board.workspace_id, user, db)
    if board.project_id is not None:
        from .workspace_models import Project
        project = db.get(Project, board.project_id)
        if project is None or project.owner_id != board.owner_id or project.workspace_id != board.workspace_id:
            raise HTTPException(404, 'Board project is outside its workspace')
        if writable and project.archived: raise HTTPException(409, 'Restore this archived project before changing its resources.')
    if writable and board.status != 'active': raise HTTPException(409, 'Restore this archived board before changing it.')
    board._actor_id = user.id
    return board


def view(board, user=None, db=None):
    from .workspace_models import Project
    project=db.get(Project,board.project_id) if db is not None and board.project_id else None
    return {'project_archived':bool(project and project.archived), **workspaces.fields(board, 'id owner_id workspace_id project_id title status current_revision created_at updated_at'),
            'role': role(board, user, db) if user else 'owner', 'ai_calls': 0}


def linked_board(cid, user, db):
    link = db.scalar(select(BoardConversation).where(BoardConversation.conversation_id == cid))
    if link is None: return None
    board = owned(link.board_id, user, db)
    conversation = db.get(Conversation, cid)
    if conversation is None or conversation.user_id != user.id or conversation.project_id != (board.project_id if board.owner_id == user.id else None):
        raise HTTPException(404, 'Conversation is outside the board scope')
    return board


def conversation_in_scope(board, cid, user, db):
    row = db.get(Conversation, cid)
    if row is None or row.user_id != user.id or row.project_id != (board.project_id if board.owner_id == user.id else None):
        raise HTTPException(404, 'Conversation not found in this board scope')
    return row


def document_in_scope(board, did, user, db):
    if board.owner_id != user.id: raise HTTPException(404, 'Private board source unavailable')
    row = db.get(Document, did)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, 'Document not found in this board scope')
    if row.project_id is not None:
        if row.project_id != board.project_id or row.scope_key != f'project:{row.project_id}':
            raise HTTPException(404, 'Document not found in this board project')
    else:
        # Conversation-scoped files require an explicit conversation association,
        # including for workspace boards without an optional project.
        conversation_in_scope(board, row.conversation_id, user, db)
        if db.get(BoardConversation, (board.id, row.conversation_id)) is None or row.scope_key != f'conversation:{row.conversation_id}':
            raise HTTPException(404, 'Document conversation is not linked to this board')
    return row


def resource_documents(board, user, db):
    rows = []
    for did in db.scalars(select(BoardResourceLink.document_id).where(BoardResourceLink.board_id == board.id).order_by(BoardResourceLink.document_id)):
        try: rows.append(document_in_scope(board, did, user, db))
        except HTTPException as exc:
            # A moved/revoked source never remains an authorization grant.
            if exc.status_code != 404: raise
    return rows


def conversation_document_ids(cid, user, db):
    board = linked_board(cid, user, db)
    return None if board is None else [row.id for row in resource_documents(board, user, db)]


def revision_view(row, *, scene=False):
    result = workspaces.fields(row, 'board_id revision schema_version restored_from created_at')
    if scene: result['scene'] = json.loads(row.scene_json)
    return {**result, 'ai_calls': 0}


def save(board, expected, scene_json, db, *, restored_from=None):
    if board.current_revision != expected:
        raise HTTPException(409, 'Scene changed. Reload before saving.')
    if board.current_revision >= MAX_REVISIONS:
        raise HTTPException(413, 'Board history limit reached (500 revisions).')
    # Cast to BLOB so SQLite counts UTF-8 bytes, including non-ASCII scene text.
    used = db.scalar(select(func.coalesce(func.sum(func.length(BoardSceneRevision.scene_json.cast(LargeBinary))), 0))
        .join(Board, Board.id == BoardSceneRevision.board_id).where(Board.owner_id == board.owner_id))
    if used + len(scene_json.encode('utf-8')) > MAX_OWNER_SCENE_BYTES:
        raise HTTPException(413, 'Board scene storage limit reached (250 MiB per owner).')
    timestamp = now()
    result = db.execute(update(Board).where(Board.id == board.id, Board.current_revision == expected).values(
        current_revision=expected + 1, updated_at=timestamp))
    if result.rowcount != 1: raise HTTPException(409, 'Scene changed. Reload before saving.')
    row = BoardSceneRevision(board_id=board.id, revision=expected + 1, schema_version=1,
                             scene_json=scene_json, restored_from=restored_from, created_at=timestamp)
    db.add(row)
    db.flush()
    return row
