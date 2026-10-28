"""Durable, owner-private Canvas jobs and immutable artifact versions."""
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, now


class GenerationJob(Base):
    __tablename__ = 'canvas_generation_jobs'
    __table_args__ = (
        UniqueConstraint('owner_id', 'request_key'),
        CheckConstraint("status IN ('queued','planning','generating','validating','rendering','completed','failed','cancelled','timed_out')"),
        Index('ix_canvas_jobs_queue', 'status', 'created_at'),
        Index('ix_canvas_jobs_owner_board', 'owner_id', 'board_id', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    board_id: Mapped[int] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'))
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True)
    artifact_id: Mapped[str] = mapped_column(String(40))
    request_key: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(String(1))
    output_format: Mapped[str] = mapped_column(String(24), default='kumuta-json-v1', server_default='kumuta-json-v1')
    status: Mapped[str] = mapped_column(String(16), default='queued')
    event_sequence: Mapped[int] = mapped_column(default=1)
    model: Mapped[str | None] = mapped_column(String(160))
    user_message_id: Mapped[int | None] = mapped_column(ForeignKey('messages.id', ondelete='SET NULL'), nullable=True)
    assistant_message_id: Mapped[int | None] = mapped_column(ForeignKey('messages.id', ondelete='SET NULL'), nullable=True)
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_started_at: Mapped[str | None] = mapped_column(String(40))
    deadline: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[int | None] = mapped_column()
    usage_id: Mapped[int | None] = mapped_column(ForeignKey('usage_records.id'))
    error: Mapped[str | None] = mapped_column(String(600))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class GenerationEvent(Base):
    __tablename__ = 'canvas_generation_events'
    job_id: Mapped[str] = mapped_column(ForeignKey('canvas_generation_jobs.id', ondelete='CASCADE'), primary_key=True)
    sequence: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    preview_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class CanvasArtifact(Base):
    __tablename__ = 'canvas_artifacts'
    __table_args__ = (UniqueConstraint('owner_id', 'request_key'),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    board_id: Mapped[int] = mapped_column(ForeignKey('canvas_boards.id', ondelete='CASCADE'))
    request_key: Mapped[str] = mapped_column(String(100))
    copied_from: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class ArtifactVersion(Base):
    __tablename__ = 'canvas_artifact_versions'
    __table_args__ = (CheckConstraint('version >= 1'), UniqueConstraint('source_job_id'))
    artifact_id: Mapped[str] = mapped_column(ForeignKey('canvas_artifacts.id', ondelete='CASCADE'), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    engine: Mapped[str] = mapped_column(String(1))
    content_json: Mapped[str] = mapped_column(Text)
    source_job_id: Mapped[str | None] = mapped_column(ForeignKey('canvas_generation_jobs.id'))
    validation_status: Mapped[str] = mapped_column(String(16), default='validated')
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class ArtifactPlacement(Base):
    __tablename__ = 'canvas_artifact_placements'
    artifact_id: Mapped[str] = mapped_column(ForeignKey('canvas_artifacts.id', ondelete='CASCADE'), primary_key=True)
    version: Mapped[int] = mapped_column()
    element_ids_json: Mapped[str] = mapped_column(Text)
    removed: Mapped[bool] = mapped_column(default=False)
    scene_revision: Mapped[int] = mapped_column()
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class ArtifactRenderReport(Base):
    __tablename__ = 'canvas_artifact_render_reports'
    artifact_id: Mapped[str] = mapped_column(ForeignKey('canvas_artifacts.id', ondelete='CASCADE'), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
