"""Explicit-consent memory routes. Manual operations never import Gemini."""
from typing import Literal, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .database import User
from .memory_models import Memory, MemorySetting
from . import memory as service, workspaces


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Scope(Strict):
    scope: Literal['global', 'project', 'conversation'] = 'global'
    project_id: Optional[int] = Field(None, gt=0)
    conversation_id: Optional[int] = Field(None, gt=0)


class Content(Strict):
    content: str = Field(min_length=1, max_length=4000)
    consent: Literal[True]

    @field_validator('content')
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or '\x00' in value:
            raise ValueError('Memory must contain text without null characters.')
        return value.strip()


class Create(Scope, Content):
    pass


class Edit(Content):
    revision: int = Field(ge=1)


class Remove(Strict):
    revision: int = Field(ge=1)


class Clear(Scope):
    confirmation: Literal['CLEAR']


class Settings(Scope):
    enabled: bool
    revision: int = Field(ge=0)


def register(app, user_dependency, db_dependency, *_):
    @app.get('/memories')
    def listing(scope: Literal['global', 'project', 'conversation', 'all'] = 'global',
                project_id: Optional[int] = None, conversation_id: Optional[int] = None,
                q: str = Query('', max_length=300), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        if scope == 'all':
            if project_id is not None or conversation_id is not None:
                raise HTTPException(422, 'All scopes cannot include a resource filter.')
            keys = list(db.scalars(select(Memory.scope_key).where(Memory.user_id == user.id).distinct()))
        else:
            keys = [service.scope_key(scope, project_id, conversation_id, user, db)]
        rows = service.search(user, keys, q, db, limit+1, offset) if keys else []
        return {'items': [service.view(r) for r in rows[:limit]], 'has_more': len(rows) > limit}

    @app.post('/memories', status_code=201)
    def add(data: Create, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        key = service.scope_key(data.scope, data.project_id, data.conversation_id, user, db, writable=True)
        digest = service.fingerprint(data.content)
        row = db.scalar(select(Memory).where(Memory.user_id == user.id, Memory.scope_key == key, Memory.fingerprint == digest))
        duplicate = row is not None
        if row is None:
            row = Memory(user_id=user.id, scope=data.scope, scope_key=key, project_id=data.project_id,
                         conversation_id=data.conversation_id, content=data.content, fingerprint=digest)
            db.add(row)
        db.commit()
        return {**service.view(row), 'duplicate': duplicate, 'ai_calls': 0}

    @app.patch('/memories/{mid}')
    def edit(mid: int, data: Edit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(mid, user, db)
        service.scope_key(row.scope, row.project_id, row.conversation_id, user, db, writable=True)
        workspaces.check_revision(row, data.revision)
        digest = service.fingerprint(data.content)
        if db.scalar(select(Memory.id).where(Memory.user_id == user.id, Memory.scope_key == row.scope_key,
                                            Memory.fingerprint == digest, Memory.id != mid)):
            raise HTTPException(409, 'This memory is already saved in this scope.')
        row.content, row.fingerprint = data.content, digest
        workspaces.touch(row)
        db.commit()
        return service.view(row)

    @app.delete('/memories/{mid}')
    def remove(mid: int, data: Remove, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(mid, user, db)
        workspaces.check_revision(row, data.revision)
        db.delete(row)
        db.commit()
        return {'ok': True, 'ai_calls': 0}

    @app.post('/memories/clear')
    def clear(data: Clear, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        key = service.scope_key(data.scope, data.project_id, data.conversation_id, user, db)
        result = db.execute(delete(Memory).where(Memory.user_id == user.id, Memory.scope_key == key))
        db.commit()
        return {'ok': True, 'deleted': result.rowcount, 'ai_calls': 0}

    @app.get('/settings/memory')
    def get_settings(scope: Literal['global', 'project', 'conversation'] = 'global', project_id: Optional[int] = None,
                     conversation_id: Optional[int] = None, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        key = service.scope_key(scope, project_id, conversation_id, user, db)
        return {**service.setting(user, key, db), 'master_enabled': service.setting(user, 'global', db)['enabled'],
                'context_token_budget': service.CONTEXT_BUDGET, 'automatic_extraction': False}

    @app.put('/settings/memory')
    def settings(data: Settings, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        key = service.scope_key(data.scope, data.project_id, data.conversation_id, user, db)
        current = service.setting(user, key, db)
        if data.revision != current['revision']:
            raise HTTPException(409, 'Memory settings changed. Reload and try again.')
        row = db.scalar(select(MemorySetting).where(MemorySetting.user_id == user.id, MemorySetting.scope_key == key))
        if row is None:
            row = MemorySetting(user_id=user.id, scope_key=key, project_id=data.project_id,
                                conversation_id=data.conversation_id, enabled=data.enabled, revision=1)
            db.add(row)
        else:
            row.enabled = data.enabled
            row.revision += 1
        db.commit()
        return service.setting(user, key, db)
