"""Private learning records. SQLite remains the sole canonical store."""
from typing import Optional
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, now


class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class Course(Record, Base):
    __tablename__ = 'study_courses'
    __table_args__ = (UniqueConstraint('id', 'project_id'), {'sqlite_autoincrement': True})
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    objectives: Mapped[str] = mapped_column(Text, default='')
    archived: Mapped[bool] = mapped_column(default=False)
    origin: Mapped[str] = mapped_column(String(10), default='manual')


class Chapter(Record, Base):
    __tablename__ = 'study_chapters'
    __table_args__ = (UniqueConstraint('id', 'course_id', 'project_id'), ForeignKeyConstraint(
        ['course_id', 'project_id'], ['study_courses.id', 'study_courses.project_id'], ondelete='CASCADE'), {'sqlite_autoincrement': True})
    course_id: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[float] = mapped_column(default=1024)


class Lesson(Record, Base):
    __tablename__ = 'study_lessons'
    __table_args__ = (ForeignKeyConstraint(['chapter_id', 'course_id', 'project_id'],
        ['study_chapters.id', 'study_chapters.course_id', 'study_chapters.project_id'], ondelete='CASCADE'),
        Index('ix_lessons_course_position', 'course_id', 'position'), {'sqlite_autoincrement': True})
    course_id: Mapped[int] = mapped_column()
    chapter_id: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[Optional[str]] = mapped_column(String(40))
    position: Mapped[float] = mapped_column(default=1024)
    origin: Mapped[str] = mapped_column(String(10), default='manual')


class CourseChild(Record):
    course_id: Mapped[int] = mapped_column(ForeignKey('study_courses.id', ondelete='CASCADE'), index=True)


class Resource(CourseChild, Base):
    __tablename__ = 'study_resources'
    __table_args__ = {'sqlite_autoincrement': True}
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, default='')
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey('documents.id', ondelete='SET NULL'))


class Quiz(CourseChild, Base):
    __tablename__ = 'study_quizzes'
    __table_args__ = {'sqlite_autoincrement': True}
    title: Mapped[str] = mapped_column(String(200))
    questions: Mapped[str] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(default=False)
    origin: Mapped[str] = mapped_column(String(10), default='manual')


class Attempt(Record, Base):
    __tablename__ = 'study_attempts'
    __table_args__ = {'sqlite_autoincrement': True}
    quiz_id: Mapped[int] = mapped_column(ForeignKey('study_quizzes.id', ondelete='CASCADE'), index=True)
    quiz_revision: Mapped[int] = mapped_column()
    result: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column()
    total: Mapped[int] = mapped_column()


class Deck(CourseChild, Base):
    __tablename__ = 'study_decks'
    __table_args__ = {'sqlite_autoincrement': True}
    title: Mapped[str] = mapped_column(String(200))


class Card(Record, Base):
    __tablename__ = 'study_cards'
    __table_args__ = (Index('ix_cards_owner_due', 'owner_id', 'due_at'), {'sqlite_autoincrement': True})
    deck_id: Mapped[int] = mapped_column(ForeignKey('study_decks.id', ondelete='CASCADE'), index=True)
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    schedule: Mapped[str] = mapped_column(Text)
    due_at: Mapped[str] = mapped_column(String(40), default=now)
    reviews: Mapped[int] = mapped_column(default=0)
    origin: Mapped[str] = mapped_column(String(10), default='manual')


class Review(Record, Base):
    __tablename__ = 'study_reviews'
    __table_args__ = {'sqlite_autoincrement': True}
    card_id: Mapped[int] = mapped_column(ForeignKey('study_cards.id', ondelete='CASCADE'), index=True)
    rating: Mapped[int] = mapped_column()
    log: Mapped[str] = mapped_column(Text)
    due_at: Mapped[str] = mapped_column(String(40))


class Plan(Record, Base):
    __tablename__ = 'study_plans'
    __table_args__ = {'sqlite_autoincrement': True}
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    target_date: Mapped[Optional[str]] = mapped_column(String(10))
    target_minutes: Mapped[int] = mapped_column(default=30)
    cadence: Mapped[str] = mapped_column(String(10), default='daily')
    milestones: Mapped[str] = mapped_column(Text, default='[]')
    sessions: Mapped[str] = mapped_column(Text, default='[]')
    origin: Mapped[str] = mapped_column(String(10), default='manual')


class PlanCourse(Base):
    __tablename__ = 'study_plan_courses'
    plan_id: Mapped[int] = mapped_column(ForeignKey('study_plans.id', ondelete='CASCADE'), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('study_courses.id', ondelete='CASCADE'), primary_key=True)


class PlanTask(Base):
    __tablename__ = 'study_plan_tasks'
    plan_id: Mapped[int] = mapped_column(ForeignKey('study_plans.id', ondelete='CASCADE'), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True)
