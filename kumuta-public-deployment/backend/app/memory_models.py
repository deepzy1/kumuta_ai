"""Canonical owner-private explicit memory. No extraction or embedding copies."""
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, now


class Memory(Base):
    __tablename__ = 'memories'
    __table_args__ = (
        UniqueConstraint('user_id', 'scope_key', 'fingerprint'),
        CheckConstraint("(scope = 'global' AND project_id IS NULL AND conversation_id IS NULL) OR "
                        "(scope = 'project' AND project_id IS NOT NULL AND conversation_id IS NULL) OR "
                        "(scope = 'conversation' AND project_id IS NULL AND conversation_id IS NOT NULL)"),
        Index('ix_memories_owner_scope', 'user_id', 'scope_key', 'updated_at'),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    scope: Mapped[str] = mapped_column(String(16))
    scope_key: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    content: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    consented_at: Mapped[str] = mapped_column(String(40), default=now)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class MemorySetting(Base):
    __tablename__ = 'memory_settings'
    __table_args__ = (UniqueConstraint('user_id', 'scope_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    scope_key: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    enabled: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=1)

