"""Private drawing boards; separate from project Kanban revisions."""
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, now


class Board(Base):
    __tablename__ = 'canvas_boards'
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'owner_id'], ['workspaces.id', 'workspaces.owner_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['project_id', 'workspace_id', 'owner_id'], ['projects.id', 'projects.workspace_id', 'projects.owner_id'], ondelete='CASCADE'),
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint('current_revision >= 0'),
        Index('ix_canvas_boards_owner_workspace', 'owner_id', 'workspace_id', 'status', 'updated_at'),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    workspace_id: Mapped[int] = mapped_column()
    project_id: Mapped[int | None] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default='active')
    current_revision: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class BoardSceneRevision(Base):
    __tablename__ = 'canvas_scene_revisions'
    __table_args__ = (CheckConstraint('revision >= 1'), CheckConstraint('schema_version = 1'))
    board_id: Mapped[int] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'), primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True)
    schema_version: Mapped[int] = mapped_column(default=1)
    scene_json: Mapped[str] = mapped_column(Text)
    restored_from: Mapped[int | None] = mapped_column()
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class BoardConversation(Base):
    __tablename__ = 'canvas_board_conversations'
    board_id: Mapped[int] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'), primary_key=True)
    # A conversation has exactly one board context, even when projects coincide.
    conversation_id: Mapped[int] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True, unique=True)


class BoardResourceLink(Base):
    __tablename__ = 'canvas_board_resources'
    board_id: Mapped[int] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)


class BoardMediaLink(Base):
    """Associations only; bytes remain in dataset or chat attachment storage."""
    __tablename__ = 'canvas_board_media'
    __table_args__ = (CheckConstraint('(dataset_id IS NOT NULL AND attachment_id IS NULL) OR (dataset_id IS NULL AND attachment_id IS NOT NULL)'),)
    board_id: Mapped[int] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'), primary_key=True)
    kind: Mapped[str] = mapped_column(String(12), primary_key=True)
    source_id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id', ondelete='CASCADE'))
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey('message_attachments.id', ondelete='CASCADE'))


class BoardMember(Base):
    __tablename__ = 'canvas_board_members'
    __table_args__ = (CheckConstraint("role IN ('editor','viewer')"),
                      CheckConstraint("status IN ('pending','accepted')"),)
    board_id: Mapped[int] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    role: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default='pending')
    reviewed_revision: Mapped[int] = mapped_column()
    created_at: Mapped[str] = mapped_column(String(40), default=now)
