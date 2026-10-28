"""Opt-in browser sessions alongside legacy bearer authentication. No token handoff."""
import hashlib
import secrets
import time
from fastapi import HTTPException
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from . import deployment

COOKIE = 'kumuta_session'
CSRF_HEADER = 'X-Kumuta-CSRF'


def decode_token(token, secret):
    """Require the expiry and identity at request, exchange and SSE boundaries."""
    import jwt
    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'], options={'require': ['exp', 'sub']})
        uid = int(payload['sub'])
        if uid <= 0:
            raise ValueError('Invalid subject')
        return payload
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        raise HTTPException(401, 'Invalid or expired session') from None


class BrowserSession(Base):
    __tablename__ = 'browser_sessions'
    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[int] = mapped_column()
    revoked: Mapped[bool] = mapped_column(default=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf(request, allowed_origins):
    origin = request.headers.get('origin', '')
    same_origin = str(request.base_url).rstrip('/')
    if request.headers.get(CSRF_HEADER) != '1' or not origin or origin not in {*allowed_origins, same_origin}:
        raise HTTPException(403, 'Browser session requires a trusted Origin and CSRF header.')


def valid(identity, uid, db):
    row = db.get(BrowserSession, identity)
    return bool(row and row.user_id == uid and not row.revoked and row.expires_at > time.time())


def issue(user, token, expiry, db, response, request):
    previous = request.cookies.get(COOKIE)
    if previous:
        old = db.get(BrowserSession, digest(previous))
        if old: old.revoked = True
    secret = secrets.token_urlsafe(48)
    db.add(BrowserSession(id_hash=digest(secret), user_id=user.id, token_hash=digest(token), expires_at=expiry))
    db.commit()
    response.set_cookie(COOKIE, secret, max_age=max(0, int(expiry-time.time())),
                        httponly=True, secure=deployment.production() or request.url.scheme == 'https', samesite='lax', path='/')


def stream_valid(request, uid, db, secret):
    """Recheck authentication on every SSE iteration, including legacy JWT expiry."""
    from .database import User
    if db.get(User,uid) is None: return False
    cookie = request.cookies.get(COOKIE)
    if cookie: return valid(digest(cookie), uid, db)
    token = request.headers.get('authorization', '').removeprefix('Bearer ')
    try:
        payload = decode_token(token, secret)
        if int(payload['sub']) != uid: return False
    except HTTPException: return False
    from sqlalchemy import select
    return not any(r.revoked or r.expires_at <= time.time() for r in db.scalars(
        select(BrowserSession).where(BrowserSession.token_hash == digest(token))))
