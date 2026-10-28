"""Owned documents, persistent processing queue, local files and page-aware chunks."""
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, now


class StoredFile(Base):
    # Separate ledger survives resource cascades so the worker can remove orphan bytes.
    __tablename__ = 'document_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Document(Base):
    __tablename__ = 'documents'
    __table_args__ = (
        UniqueConstraint('user_id', 'scope_key', 'sha256'),
        CheckConstraint('(project_id IS NOT NULL AND conversation_id IS NULL) OR '
                        '(project_id IS NULL AND conversation_id IS NOT NULL)'),
        CheckConstraint("status IN ('queued', 'processing', 'ready', 'error')"),
        Index('ix_documents_owner_scope', 'user_id', 'scope_key', 'created_at'),
        Index('ix_documents_queue', 'status', 'started_at'),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    scope_key: Mapped[str] = mapped_column(String(64))
    file_id: Mapped[int] = mapped_column(ForeignKey('document_files.id'), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default='queued')
    error: Mapped[Optional[str]] = mapped_column(String(300))
    warning: Mapped[Optional[str]] = mapped_column(String(500))
    pages: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    job_token: Mapped[Optional[str]] = mapped_column(String(40))
    started_at: Mapped[Optional[str]] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class DocumentChunk(Base):
    __tablename__ = 'document_chunks'
    __table_args__ = (UniqueConstraint('document_id', 'ordinal'), Index('ix_chunks_document', 'document_id', 'ordinal'), {'sqlite_autoincrement': True})
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'))
    ordinal: Mapped[int] = mapped_column()
    page: Mapped[Optional[int]] = mapped_column()
    section: Mapped[str] = mapped_column(String(120), default='')
    content: Mapped[str] = mapped_column(Text)
