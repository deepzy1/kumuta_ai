"""Existing SQLite tables plus additive, repeatable schema upgrades."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


DB_URL = os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "chat.db"}')
engine = create_engine(DB_URL, connect_args={'check_same_thread': False, 'timeout': 30} if DB_URL.startswith('sqlite') else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


if DB_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_settings(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_model: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    allow_paid_models: Mapped[int] = mapped_column(default=0)
    canvas_generation_mode: Mapped[str] = mapped_column(String(16), default='auto', server_default='auto')


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(120), default='New chat')
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
    generation_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    generation_started: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    quickui_appearance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    messages: Mapped[list['Message']] = relationship(cascade='all, delete-orphan', order_by='Message.id')
    summaries: Mapped[list['Summary']] = relationship(cascade='all, delete-orphan')


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey('conversations.id'), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    attachment_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attachment_mime: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    attachment_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachment_size: Mapped[Optional[int]] = mapped_column(nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    status: Mapped[str] = mapped_column(String(20), default='complete')
    active: Mapped[int] = mapped_column(default=1)
    quickui_appearance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grounding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_request: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quickui: Mapped[Optional['QuickUIResponse']] = relationship(cascade='all, delete-orphan', uselist=False, lazy='selectin')
    attachments: Mapped[list['Attachment']] = relationship(cascade='all, delete-orphan', order_by='Attachment.id', lazy='selectin')


class Attachment(Base):
    __tablename__ = 'message_attachments'
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey('messages.id'), index=True)
    attachment_name: Mapped[str] = mapped_column(String(255))
    attachment_mime: Mapped[str] = mapped_column(String(100))
    attachment_size: Mapped[int] = mapped_column()
    attachment_data: Mapped[str] = mapped_column(Text)


class Summary(Base):
    __tablename__ = 'conversation_summaries'
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey('conversations.id'), index=True)
    through_message_id: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    active: Mapped[int] = mapped_column(default=1)


class Usage(Base):
    __tablename__ = 'usage_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(index=True, nullable=True)
    model: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20), default='chat')
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    estimated: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(24))
    error_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    web_search: Mapped[int] = mapped_column(default=0)
    search_queries: Mapped[Optional[int]] = mapped_column(nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    quickui: Mapped[int] = mapped_column(default=0)


class QuickUIResponse(Base):
    """Content only. Appearance never enters this immutable model specification."""
    __tablename__ = 'quickui_responses'
    message_id: Mapped[int] = mapped_column(ForeignKey('messages.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    specification: Mapped[str] = mapped_column(Text)
    introduction: Mapped[str] = mapped_column(Text, default='')
    parse_ms: Mapped[int] = mapped_column(default=0)
    interaction_state: Mapped[str] = mapped_column(Text, default='{}')
    state_revision: Mapped[int] = mapped_column(default=0)


class QuickUIPreference(Base):
    __tablename__ = 'quickui_preferences'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    preferences: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class QuickUIPalette(Base):
    __tablename__ = 'quickui_palettes'
    __table_args__ = (UniqueConstraint('user_id', 'kind', 'fingerprint'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(60), default='Custom palette')
    fingerprint: Mapped[str] = mapped_column(String(64))
    selection: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


# Constant SQL declarations only; no user-controlled identifiers or values.
ADDITIONS = {
    'quickui_responses': {'introduction': "TEXT NOT NULL DEFAULT ''"},
    'usage_records': {'web_search': 'INTEGER NOT NULL DEFAULT 0', 'search_queries': 'INTEGER', 'latency_ms': 'INTEGER', 'quickui': 'INTEGER NOT NULL DEFAULT 0'},
    'conversation_summaries': {'active': 'INTEGER NOT NULL DEFAULT 1'},
    'users': {'encrypted_api_key': 'TEXT', 'preferred_model': 'VARCHAR(160)', 'allow_paid_models': 'INTEGER NOT NULL DEFAULT 0'},
    'conversations': {'created_at': "VARCHAR(40) NOT NULL DEFAULT ''", 'updated_at': "VARCHAR(40) NOT NULL DEFAULT ''", 'generation_id': 'VARCHAR(40)', 'generation_started': 'VARCHAR(40)'},
    'messages': {'attachment_size': 'INTEGER', 'model': 'VARCHAR(160)', 'created_at': "VARCHAR(40) NOT NULL DEFAULT ''", 'status': "VARCHAR(20) NOT NULL DEFAULT 'complete'", 'active': 'INTEGER NOT NULL DEFAULT 1'},
}
ADDITIONS['conversations']['quickui_appearance'] = 'TEXT'
ADDITIONS['conversations']['project_id'] = 'INTEGER REFERENCES projects(id) ON DELETE SET NULL'
ADDITIONS['messages'].update({'quickui_appearance': 'TEXT', 'grounding': 'TEXT'})
ADDITIONS['messages'].update({'document_request': 'TEXT', 'document_sources': 'TEXT'})
ADDITIONS['focus_sessions'] = {'segments': "TEXT NOT NULL DEFAULT '[]'"}
ADDITIONS['time_entries'] = {'segments': "TEXT NOT NULL DEFAULT '[]'", 'adjusted': 'BOOLEAN NOT NULL DEFAULT 0', 'allocation_estimated': 'BOOLEAN NOT NULL DEFAULT 0'}


ADDITIONS['tasks'] = {'completed_at': 'VARCHAR(40)'}
ADDITIONS['study_lessons'] = {'completed_at': 'VARCHAR(40)'}
ADDITIONS['project_notes'] = {'pinned': 'BOOLEAN NOT NULL DEFAULT 0'}

def migrate():
    # Register all tables before inspecting schema, including fresh databases.
    from . import workspace_models, memory_models, document_models, study_models, focus_models, dataset_models, report_models, board_models, canvas_generation_models, browser_sessions
    from .migrations import MIGRATIONS
    sqlite = engine.url.get_backend_name() == 'sqlite'
    file_database = sqlite and engine.url.database not in (None, ':memory:')
    with engine.begin() as connection:
        if sqlite:
            # Serialize startup migrations before inspecting schema. A second
            # process sees committed columns instead of attempting duplicate ALTERs.
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        existing = inspect(connection)
        tables = set(existing.get_table_names())
        changes = [(table, column, declaration) for table, columns in ADDITIONS.items()
                   if table in tables for column, declaration in columns.items()
                   if column not in {c['name'] for c in existing.get_columns(table)}]
        missing_tables = set(Base.metadata.tables) - tables
        applied = set(connection.scalars(text('SELECT version FROM schema_migrations'))) if 'schema_migrations' in tables else set()
        pending = set(MIGRATIONS) - applied
        if file_database and tables and (changes or missing_tables or pending):
            path = Path(engine.url.database)
            backup = path.with_name(f'{path.name}.pre-kumuta-{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")}.bak')
            descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Database backup integrity check failed; migration aborted.')
            os.chmod(backup, 0o600)
        for table, column, declaration in changes:
            connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}'))
        # Original rows have no historical timestamps. Keep them unknown.
        Base.metadata.create_all(connection)
        connection.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at VARCHAR(40) NOT NULL)'))
        for version in (1, 2):
            if not connection.scalar(text('SELECT version FROM schema_migrations WHERE version=:version'), {'version': version}):
                connection.execute(text('INSERT INTO schema_migrations VALUES (:version, :date)'), {'version': version, 'date': now()})
        for version in sorted(pending):
            MIGRATIONS[version](connection, now())
            connection.execute(text('INSERT INTO schema_migrations VALUES (:version, :date)'), {'version': version, 'date': now()})
    if file_database:
        os.chmod(engine.url.database, 0o600)


if __name__ == '__main__':
    raise SystemExit('Run python -m app.migrate from the backend directory.')
