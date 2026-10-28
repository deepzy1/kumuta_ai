"""Owner-private workspace foundation; no AI or document storage dependencies."""
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, now


class Workspace(Base):
    __tablename__ = 'workspaces'
    __table_args__ = (UniqueConstraint('id', 'owner_id'),
                     CheckConstraint('personal_owner_id IS NULL OR personal_owner_id = owner_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    personal_owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class WorkspaceMember(Base):
    """Only owner memberships are supported in Phase 1A."""
    __tablename__ = 'workspace_members'
    __table_args__ = (CheckConstraint("role = 'owner'"),
                     ForeignKeyConstraint(['workspace_id', 'user_id'], ['workspaces.id', 'workspaces.owner_id'], ondelete='CASCADE'))
    workspace_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default='owner')


class Project(Base):
    __tablename__ = 'projects'
    __table_args__ = (ForeignKeyConstraint(['workspace_id', 'owner_id'], ['workspaces.id', 'workspaces.owner_id'], ondelete='CASCADE'),
                     Index('ix_projects_workspace_archived', 'workspace_id', 'archived'),
                     Index('ux_projects_canvas_scope', 'id', 'workspace_id', 'owner_id', unique=True))
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column()
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default='')
    icon: Mapped[str] = mapped_column(String(32), default='folder')
    color: Mapped[str] = mapped_column(String(7), default='#ea580c')
    archived: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=1)
    board_revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class TaskColumn(Base):
    __tablename__ = 'task_columns'
    __table_args__ = (UniqueConstraint('id', 'project_id'), Index('ix_columns_project_position', 'project_id', 'position'))
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[float] = mapped_column()
    is_done: Mapped[bool] = mapped_column(default=False)


class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (
        UniqueConstraint('id', 'project_id'),
        ForeignKeyConstraint(['column_id', 'project_id'], ['task_columns.id', 'task_columns.project_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['parent_id', 'project_id'], ['tasks.id', 'tasks.project_id'], ondelete='CASCADE'),
        CheckConstraint('parent_id IS NULL OR parent_id != id'),
        CheckConstraint("priority IN ('none', 'low', 'medium', 'high', 'urgent')"),
        Index('ix_tasks_project_column_position', 'project_id', 'column_id', 'position'),
        Index('ix_tasks_parent', 'parent_id'),
        Index('ix_tasks_project_due', 'project_id', 'due_date'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    column_id: Mapped[int] = mapped_column()
    parent_id: Mapped[Optional[int]] = mapped_column()
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    priority: Mapped[str] = mapped_column(String(12), default='none')
    due_date: Mapped[Optional[str]] = mapped_column(String(10))
    position: Mapped[float] = mapped_column()
    completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[Optional[str]] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class ChecklistItem(Base):
    __tablename__ = 'task_checklist_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(String(300))
    completed: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column()


class Note(Base):
    __tablename__ = 'project_notes'
    __table_args__ = (Index('ix_notes_project_updated', 'project_id', 'updated_at'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default='')
    pinned: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class TaskDocument(Base):
    """Reference an existing file without storing another copy."""
    __tablename__ = 'task_documents'
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
