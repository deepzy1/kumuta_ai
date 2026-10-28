"""Authenticated appearance storage; no provider calls and no conversational memory writes."""
import hashlib
import json
from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session
from .database import Message, QuickUIPalette, QuickUIPreference, User, now
from .quickui import Appearance, Color, Preferences, Strict

class SavePreferences(Strict):
    preferences: Preferences
    revision: int = Field(ge=0)

class SavePalette(Strict):
    selection: Color
    name: str = Field(default='Custom palette', min_length=1, max_length=60)

class Override(Strict):
    appearance: Appearance | None = None


class Interaction(Strict):
    state: dict
    revision: int = Field(ge=0)


def preferences_for(user_id, db):
    row = db.get(QuickUIPreference, user_id)
    return {'preferences': Preferences.model_validate_json(row.preferences).model_dump() if row else Preferences().model_dump(),
            'revision': row.revision if row else 0}


def serialize_palette(row):
    return {'id': row.id, 'name': row.name, 'selection': json.loads(row.selection)}


def palettes_for(user_id, db):
    rows = list(db.scalars(select(QuickUIPalette).where(QuickUIPalette.user_id == user_id)
                          .order_by(QuickUIPalette.updated_at.desc(), QuickUIPalette.id.desc())))
    return {'recent': [serialize_palette(r) for r in rows if r.kind == 'recent'],
            'saved': [serialize_palette(r) for r in rows if r.kind == 'saved']}


def lock_user(user, db):
    # Serialize preference/palette writes per user, including across backend processes.
    # This uses normal SQL row locking and stays portable to PostgreSQL.
    db.execute(update(User).where(User.id == user.id).values(allow_paid_models=User.allow_paid_models))


def record_palette(user_id, selection, name, kind, db):
    encoded = json.dumps(selection, sort_keys=True, separators=(',', ':'))
    canonical = selection if selection['mode'] == 'gradient' else {'mode': 'system' if selection['mode'] == 'system' else 'solid', 'colors': selection['colors']}
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    row = db.scalar(select(QuickUIPalette).where(QuickUIPalette.user_id == user_id,
                    QuickUIPalette.kind == kind, QuickUIPalette.fingerprint == fingerprint))
    if not row:
        if kind == 'saved' and db.scalar(select(func.count()).select_from(QuickUIPalette)
                .where(QuickUIPalette.user_id == user_id, QuickUIPalette.kind == kind)) >= 40:
            raise HTTPException(422, 'Save up to 40 palettes. Remove one before adding another.')
        row = QuickUIPalette(user_id=user_id, kind=kind, fingerprint=fingerprint, selection=encoded)
        db.add(row)
    row.name, row.updated_at, row.selection = name, now(), encoded
    db.flush()
    if kind == 'recent':
        old = list(db.scalars(select(QuickUIPalette.id).where(QuickUIPalette.user_id == user_id,
                     QuickUIPalette.kind == 'recent').order_by(QuickUIPalette.updated_at.desc(), QuickUIPalette.id.desc()).offset(16)))
        if old:
            db.execute(delete(QuickUIPalette).where(QuickUIPalette.id.in_(old)))


def register(app, user_dependency, db_dependency, owned):
    @app.put('/conversations/{cid}/messages/{mid}/quickui-state')
    def interaction(cid: int, mid: int, data: Interaction, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        owned(cid, user, db)
        lock_user(user, db)
        message = db.get(Message, mid)
        if not message or message.conversation_id != cid or not message.quickui or message.quickui.user_id != user.id:
            raise HTTPException(404, 'QuickUI response not found')
        from .canvas_artifacts import validate_state
        from .quickui import Specification
        row = message.quickui
        if data.revision != row.state_revision:
            raise HTTPException(409, 'Component state changed. Reload this conversation before saving again.')
        if len(json.dumps(data.state).encode()) > 32000:
            raise HTTPException(413, 'Component state exceeds 32000 bytes.')
        try:
            validate_state(Specification.model_validate_json(row.specification), data.state)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        row.interaction_state = json.dumps(data.state, allow_nan=False)
        row.state_revision += 1
        db.commit()
        return {'state': data.state, 'revision': row.state_revision, 'ai_calls': 0}

    @app.get('/settings/quickui')
    def get_preferences(user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        return {**preferences_for(user.id, db), **palettes_for(user.id, db)}

    @app.put('/settings/quickui')
    def save_preferences(data: SavePreferences, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        lock_user(user, db)
        row = db.get(QuickUIPreference, user.id)
        if data.revision != (row.revision if row else 0):
            raise HTTPException(409, 'QuickUI preferences changed on another device. Reload preferences and try again.')
        if not row:
            row = QuickUIPreference(user_id=user.id, preferences='{}', revision=0)
            db.add(row)
        # Older clients send only QuickUI defaults. Preserve Canvas overrides
        # when the additive field was omitted from that request.
        if 'canvas' not in data.preferences.model_fields_set:
            data.preferences.canvas = Preferences.model_validate_json(row.preferences).canvas
        row.preferences = data.preferences.model_dump_json()
        row.revision += 1
        row.updated_at = now()
        record_palette(user.id, data.preferences.color.model_dump(), 'Current color', 'recent', db)
        db.commit()
        return {**preferences_for(user.id, db), **palettes_for(user.id, db)}

    @app.post('/settings/quickui/reset')
    def reset(data: SavePreferences, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        # Retain monotonic revisions so stale devices cannot overwrite a reset.
        return save_preferences(SavePreferences(preferences=Preferences(), revision=data.revision), user, db)

    @app.post('/settings/quickui/palettes/{kind}')
    def save_palette(kind: str, data: SavePalette, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        if kind not in ('recent', 'saved'):
            raise HTTPException(404, 'Palette collection not found')
        lock_user(user, db)
        record_palette(user.id, data.selection.model_dump(), data.name, kind, db)
        if kind == 'saved':
            record_palette(user.id, data.selection.model_dump(), data.name, 'recent', db)
        db.commit()
        return palettes_for(user.id, db)

    @app.delete('/settings/quickui/palettes/{kind}')
    def clear_palettes(kind: str, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        if kind not in ('recent', 'saved'):
            raise HTTPException(404, 'Palette collection not found')
        lock_user(user, db)
        db.execute(delete(QuickUIPalette).where(QuickUIPalette.user_id == user.id, QuickUIPalette.kind == kind))
        db.commit()
        return palettes_for(user.id, db)

    @app.delete('/settings/quickui/palette/{pid}')
    def remove_palette(pid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        lock_user(user, db)
        row = db.get(QuickUIPalette, pid)
        if not row or row.user_id != user.id:
            raise HTTPException(404, 'Palette not found')
        db.delete(row)
        db.commit()
        return palettes_for(user.id, db)

    @app.put('/conversations/{cid}/quickui-appearance')
    def chat_appearance(cid: int, data: Override, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        chat = owned(cid, user, db)
        chat.quickui_appearance = data.appearance.model_dump_json() if data.appearance else None
        db.commit()
        return {'appearance': json.loads(chat.quickui_appearance) if chat.quickui_appearance else None}

    @app.put('/conversations/{cid}/messages/{mid}/quickui-appearance')
    def response_appearance(cid: int, mid: int, data: Override, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        owned(cid, user, db)
        message = db.get(Message, mid)
        if not message or message.conversation_id != cid or not message.quickui or message.quickui.user_id != user.id:
            raise HTTPException(404, 'QuickUI response not found')
        message.quickui_appearance = data.appearance.model_dump_json() if data.appearance else None
        db.commit()
        return {'appearance': json.loads(message.quickui_appearance) if message.quickui_appearance else None}
