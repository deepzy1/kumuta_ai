"""Owned declarative reports retain configurations, never executable code/results."""
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, now


class DataReport(Base):
    __tablename__ = 'data_reports'
    __table_args__ = (Index('ix_data_reports_owner_project', 'owner_id', 'project_id', 'updated_at'), {'sqlite_autoincrement': True})
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000), default='')
    configuration: Mapped[str] = mapped_column(Text, default='[]')
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
