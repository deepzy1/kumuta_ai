"""Explicit existing-account invitations, stable identities and revocable membership."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import EmailStr, Field
from sqlalchemy import func, select
from . import boards, workspaces
from .board_models import Board, BoardMember
from .canvas_artifacts import Strict
from .database import User


class Invite(Strict):
    email: EmailStr
    role: Literal['editor', 'viewer']
    reviewed_revision: int = Field(ge=0)
    content_reviewed: Literal[True]


class RoleChange(Strict):
    role: Literal['editor', 'viewer']


def register(app, user_dependency, db_dependency):
    router = APIRouter()

    @router.get('/shared-boards')
    def inbox(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000), user=Depends(user_dependency), db=Depends(db_dependency)):
        rows = list(db.execute(select(Board, BoardMember).join(BoardMember, BoardMember.board_id==Board.id)
            .where(BoardMember.user_id==user.id).order_by(Board.updated_at.desc(), Board.id.desc()).offset(offset).limit(limit+1)))
        return {'items': [{**boards.view(board,user,db), 'invitation_status': member.status,
                          'owner': db.get(User,board.owner_id).email} for board,member in rows[:limit]],
                'has_more': len(rows)>limit, 'ai_calls': 0}

    @router.get('/boards/{bid}/sharing')
    def listing(bid: int, user=Depends(user_dependency), db=Depends(db_dependency)):
        board = boards.owned(bid,user,db)
        owner = db.get(User,board.owner_id)
        members = []
        if board.owner_id == user.id:
            members = [{'user_id': row.user_id, 'email': account.email, 'role': row.role, 'status': row.status}
                for row,account in db.execute(select(BoardMember,User).join(User,User.id==BoardMember.user_id)
                    .where(BoardMember.board_id==bid).order_by(BoardMember.created_at,BoardMember.user_id))]
        return {'owner': {'user_id': owner.id, 'email': owner.email}, 'members': members,
                'role': boards.role(board,user,db), 'current_revision': board.current_revision,
                'policy': 'Saved content and scene history are shared. Original sources and personal chats remain private.'}

    @router.post('/boards/{bid}/sharing', status_code=201)
    def invite(bid: int, data: Invite, user=Depends(user_dependency), db=Depends(db_dependency)):
        workspaces.lock_writes(user,db)
        board = boards.owned(bid,user,db,owner_only=True)
        if board.current_revision != data.reviewed_revision:
            raise HTTPException(409,'Board changed after content review. Review the current scene and history again.')
        target = db.scalar(select(User).where(User.email==str(data.email).lower()))
        if not target: raise HTTPException(404,'Existing account not found. Ask the collaborator for their exact account email.')
        if target.id == user.id: raise HTTPException(422,'The owner cannot be invited, demoted or transferred.')
        old = db.get(BoardMember,(bid,target.id))
        if old: raise HTTPException(409,'This account already has an invitation or membership. Change its role or revoke it.')
        if db.scalar(select(func.count()).select_from(BoardMember).where(BoardMember.board_id==bid)) >= 100:
            raise HTTPException(413,'Use at most 100 collaborators per board.')
        db.add(BoardMember(board_id=bid,user_id=target.id,role=data.role,reviewed_revision=data.reviewed_revision))
        db.commit()
        return {'user_id':target.id,'role':data.role,'status':'pending','ai_calls':0}

    @router.patch('/boards/{bid}/sharing/{uid}')
    def change(bid: int, uid: int, data: RoleChange, user=Depends(user_dependency), db=Depends(db_dependency)):
        workspaces.lock_writes(user,db);board=boards.owned(bid,user,db,owner_only=True)
        if uid==board.owner_id: raise HTTPException(422,'Ownership cannot change through collaborator roles.')
        row=db.get(BoardMember,(bid,uid))
        if not row: raise HTTPException(404,'Collaborator not found')
        row.role=data.role;db.commit();return {'ok':True,'ai_calls':0}

    @router.delete('/boards/{bid}/sharing/{uid}')
    def revoke(bid: int, uid: int, user=Depends(user_dependency), db=Depends(db_dependency)):
        workspaces.lock_writes(user,db);boards.owned(bid,user,db,owner_only=True)
        row=db.get(BoardMember,(bid,uid))
        if not row: raise HTTPException(404,'Collaborator not found')
        db.delete(row);db.commit();return {'ok':True,'ai_calls':0}

    @router.post('/boards/{bid}/invitation/accept')
    def accept(bid: int, user=Depends(user_dependency), db=Depends(db_dependency)):
        workspaces.lock_writes(user,db)
        row=db.get(BoardMember,(bid,user.id))
        if not row: raise HTTPException(404,'Invitation not found or revoked')
        row.status='accepted';db.commit();return {'ok':True,'ai_calls':0}

    @router.delete('/boards/{bid}/invitation')
    def decline(bid: int, user=Depends(user_dependency), db=Depends(db_dependency)):
        workspaces.lock_writes(user,db);row=db.get(BoardMember,(bid,user.id))
        if not row: raise HTTPException(404,'Invitation not found or revoked')
        db.delete(row);db.commit();return {'ok':True,'ai_calls':0}

    app.include_router(router)
