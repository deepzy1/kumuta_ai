"""Private goals, durable sessions, preferences and reusable time entries."""
from typing import Optional
from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, now
from .study_models import Record

class Goal(Record, Base):
    __tablename__ = 'focus_goals'
    __table_args__ = {'sqlite_autoincrement': True}
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    target_date: Mapped[Optional[str]] = mapped_column(String(10))
    milestones: Mapped[str] = mapped_column(Text, default='[]')
    status: Mapped[str] = mapped_column(String(12), default='active')

class GoalTask(Base):
    __tablename__ = 'focus_goal_tasks'
    goal_id: Mapped[int] = mapped_column(ForeignKey('focus_goals.id', ondelete='CASCADE'), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True)

class Session(Base):
    __tablename__ = 'focus_sessions'
    __table_args__ = (
        CheckConstraint("kind IN ('focus','short_break','long_break','tracking')"),
        CheckConstraint("status IN ('running','paused','completed','stopped')"),
        CheckConstraint('elapsed_seconds >= 0'),
        CheckConstraint('planned_seconds IS NULL OR planned_seconds BETWEEN 1 AND 86400'),
        Index('ix_focus_one_active_owner', 'owner_id', unique=True, sqlite_where=text("status IN ('running','paused')")),
        Index('ix_focus_owner_started', 'owner_id', 'started_at'), {'sqlite_autoincrement': True})
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey('projects.id', ondelete='SET NULL'), index=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey('tasks.id', ondelete='SET NULL'))
    kind: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default='running')
    planned_seconds: Mapped[Optional[int]] = mapped_column()
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0)
    started_at: Mapped[str] = mapped_column(String(40), default=now)
    running_since: Mapped[Optional[str]] = mapped_column(String(40), default=now)
    ended_at: Mapped[Optional[str]] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default='')
    revision: Mapped[int] = mapped_column(default=1)

    segments: Mapped[str] = mapped_column(Text, default='[]')

class TimeEntry(Base):
    __tablename__ = 'time_entries'
    __table_args__ = (CheckConstraint('duration_seconds >= 0'),
        Index('ix_time_owner_start', 'owner_id', 'started_at'), {'sqlite_autoincrement': True})
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey('projects.id', ondelete='SET NULL'), index=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey('tasks.id', ondelete='SET NULL'))
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey('focus_sessions.id', ondelete='SET NULL'), unique=True)
    started_at: Mapped[str] = mapped_column(String(40))
    ended_at: Mapped[str] = mapped_column(String(40))
    duration_seconds: Mapped[float] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default='')
    revision: Mapped[int] = mapped_column(default=1)

    segments: Mapped[str] = mapped_column(Text, default='[]')
    adjusted: Mapped[bool] = mapped_column(default=False)
    allocation_estimated: Mapped[bool] = mapped_column(default=False)

class Preference(Base):
    __tablename__ = 'focus_preferences'
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    focus_seconds: Mapped[int] = mapped_column(default=1500)
    short_break_seconds: Mapped[int] = mapped_column(default=300)
    long_break_seconds: Mapped[int] = mapped_column(default=900)
    revision: Mapped[int] = mapped_column(default=1)
