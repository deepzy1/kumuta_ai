"""Private source files and bounded schema metadata; source rows are not duplicated."""
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, now


class Dataset(Base):
    __tablename__ = 'datasets'
    __table_args__ = (
        UniqueConstraint('owner_id', 'project_id', 'sha256'),
        UniqueConstraint('owner_id', 'board_id', 'sha256'),
        UniqueConstraint('owner_id', 'conversation_id', 'sha256'),
        CheckConstraint('(project_id IS NOT NULL) + (board_id IS NOT NULL) + (conversation_id IS NOT NULL) = 1'),
        CheckConstraint("status IN ('queued','processing','ready','error')"),
        Index('ix_datasets_owner_project', 'owner_id', 'project_id', 'created_at'),
        Index('ix_datasets_queue', 'status', 'started_at'),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    project_id: Mapped[int | None] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    board_id: Mapped[int | None] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'))
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    file_id: Mapped[int] = mapped_column(ForeignKey('document_files.id'), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(8))
    size: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default='queued')
    error: Mapped[str | None] = mapped_column(String(300))
    metadata_json: Mapped[str] = mapped_column(Text, default='[]')
    job_token: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(default=0)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
