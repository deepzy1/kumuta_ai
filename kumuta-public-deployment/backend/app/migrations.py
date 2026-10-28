"""Numbered data migrations; invoked inside database.migrate's write transaction."""
import re
import time

from sqlalchemy import text


def workspace_foundation(connection, timestamp):
    # No user content is rewritten. A UNIQUE personal_owner_id makes this repeatable.
    connection.execute(text('''INSERT INTO workspaces
        (owner_id, personal_owner_id, name, revision, created_at, updated_at)
        SELECT id, id, 'Personal workspace', 1, :date, :date FROM users
        WHERE NOT EXISTS (SELECT 1 FROM workspaces WHERE personal_owner_id = users.id)'''), {'date': timestamp})
    connection.execute(text('''INSERT INTO workspace_members (workspace_id, user_id, role)
        SELECT id, owner_id, 'owner' FROM workspaces
        WHERE NOT EXISTS (SELECT 1 FROM workspace_members WHERE workspace_id = workspaces.id AND user_id = workspaces.owner_id)'''))
    # create_all cannot add indexes to an existing table.
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_conversations_project_id ON conversations (project_id)'))


def memory_foundation(connection, timestamp):
    connection.exec_driver_sql("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, tokenize='unicode61')")
    connection.exec_driver_sql('INSERT INTO memory_fts(rowid, content) SELECT id, content FROM memories')
    connection.exec_driver_sql('''CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content); END''')
    connection.exec_driver_sql('''CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
        DELETE FROM memory_fts WHERE rowid=old.id; END''')
    connection.exec_driver_sql('''CREATE TRIGGER memories_au AFTER UPDATE OF content ON memories BEGIN
        DELETE FROM memory_fts WHERE rowid=old.id;
        INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content); END''')


def document_foundation(connection, timestamp):
    connection.exec_driver_sql("CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(content, tokenize='unicode61')")
    connection.exec_driver_sql('INSERT INTO document_fts(rowid, content) SELECT id, content FROM document_chunks')
    connection.exec_driver_sql('''CREATE TRIGGER chunks_ai AFTER INSERT ON document_chunks BEGIN
        INSERT INTO document_fts(rowid, content) VALUES (new.id, new.content); END''')
    connection.exec_driver_sql('''CREATE TRIGGER chunks_ad AFTER DELETE ON document_chunks BEGIN
        DELETE FROM document_fts WHERE rowid=old.id; END''')
    connection.exec_driver_sql('''CREATE TRIGGER chunks_au AFTER UPDATE OF content ON document_chunks BEGIN
        DELETE FROM document_fts WHERE rowid=old.id;
        INSERT INTO document_fts(rowid, content) VALUES (new.id, new.content); END''')


def stable_context_ids(connection, timestamp):
    """Upgrade intermediate development tables without losing rows or indexes.

    Fresh installations already use AUTOINCREMENT and do not rebuild. Older
    live-reloaded drafts need SQLite's normal transactional table-copy upgrade.
    Only the three new context tables change; legacy chat tables stay intact.
    """
    names = ('memories', 'documents', 'document_chunks')
    definitions = {name: connection.scalar(text('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=:name'),
                                          {'name': name}) for name in names}
    if all('AUTOINCREMENT' in sql.upper() for sql in definitions.values()):
        return
    # Keep any sequences from partially upgraded drafts, and avoid reusing IDs
    # that were handed to clients but deleted before this compatibility upgrade.
    floor = time.time_ns() // 1_000_000
    sequences = dict(connection.execute(text('SELECT name, seq FROM sqlite_sequence')).all()) if connection.scalar(
        text("SELECT count(*) FROM sqlite_master WHERE name='sqlite_sequence'")) else {}
    objects = connection.execute(text("SELECT sql FROM sqlite_master WHERE type IN ('index','trigger') "
        "AND tbl_name IN ('memories','documents','document_chunks') AND sql IS NOT NULL")).scalars().all()
    connection.exec_driver_sql('PRAGMA legacy_alter_table=OFF')
    for name, original in definitions.items():
        sql = re.sub(r'^(CREATE TABLE\s+)(?:"' + name + '"|' + name + r')(?=\s|\()',
                     r'\1"_kumuta_' + name + '"', original, count=1, flags=re.I)
        if 'AUTOINCREMENT' not in sql.upper():
            sql = re.sub(r'(?m)^([ \t]*id INTEGER(?: NOT NULL)?)(?: PRIMARY KEY)?(,?)[ \t]*$',
                         r'\1 PRIMARY KEY AUTOINCREMENT\2', sql, count=1)
            sql = re.sub(r'\n\s*PRIMARY KEY\s*\(id\),', '', sql, count=1)
            if 'AUTOINCREMENT' not in sql.upper():
                raise RuntimeError('Unsupported context ID schema; compatibility migration rolled back.')
        if name == 'document_chunks':
            sql = re.sub(r'REFERENCES\s+(?:"documents"|documents)(?=\s|\()',
                         'REFERENCES "_kumuta_documents"', sql)
        connection.exec_driver_sql(sql)
        columns = [row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{name}")')]
        quoted = ','.join('"' + column.replace('"', '""') + '"' for column in columns)
        connection.exec_driver_sql(f'INSERT INTO "_kumuta_{name}" ({quoted}) SELECT {quoted} FROM "{name}"')
    # Copied chunks refer to the temporary documents table, so dropping originals
    # cannot cascade into the preserved copy. RENAME updates the copied FK.
    for name in ('document_chunks', 'documents', 'memories'):
        connection.exec_driver_sql(f'DROP TABLE "{name}"')
    for name in ('documents', 'document_chunks', 'memories'):
        connection.exec_driver_sql(f'ALTER TABLE "_kumuta_{name}" RENAME TO "{name}"')
        minimum = max(floor, sequences.get(name, 0))
        connection.execute(text('INSERT INTO sqlite_sequence(name,seq) SELECT :name,:seq '
            'WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name=:name)'), {'name': name, 'seq': minimum})
        connection.execute(text('UPDATE sqlite_sequence SET seq=MAX(seq,:seq) WHERE name=:name'), {'name': name, 'seq': minimum})
    for sql in objects:
        connection.exec_driver_sql(sql)
    for index, table in (('memory_fts', 'memories'), ('document_fts', 'document_chunks')):
        connection.exec_driver_sql(f'DELETE FROM {index}')
        connection.exec_driver_sql(f'INSERT INTO {index}(rowid,content) SELECT id,content FROM {table}')


MIGRATIONS = {3: workspace_foundation, 4: memory_foundation, 5: document_foundation, 6: stable_context_ids}


def study_foundation(connection, timestamp):
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_study_courses_owner_archive ON study_courses(owner_id,project_id,archived)')
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_study_attempts_quiz_created ON study_attempts(quiz_id,created_at)')

MIGRATIONS[7] = study_foundation


def focus_foundation(connection, timestamp):
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_focus_goals_owner_status ON focus_goals(owner_id,project_id,status)')

MIGRATIONS[8] = focus_foundation


def focus_segment_compatibility(connection, timestamp):
    # A running development server may create v8 during live reload before
    # the segment ledger was added. Never invent exact pause intervals.
    connection.exec_driver_sql("UPDATE time_entries SET allocation_estimated=1 WHERE segments='[]' AND duration_seconds>0")
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_study_courses_owner_archive ON study_courses(owner_id,project_id,archived)')
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_study_attempts_quiz_created ON study_attempts(quiz_id,created_at)')
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_focus_goals_owner_status ON focus_goals(owner_id,project_id,status)')

MIGRATIONS[9] = focus_segment_compatibility



def analytics_foundation(connection, timestamp):
    # Historical completion instants are unknown: do not backfill from edits.
    for table in ('tasks', 'study_lessons'):
        connection.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_{table}_project_completed_at ON {table}(project_id,completed_at)")
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS {table}_completion_insert
            AFTER INSERT ON {table} WHEN NEW.completed=1 BEGIN
            UPDATE {table} SET completed_at=strftime('%Y-%m-%dT%H:%M:%f+00:00','now') WHERE id=NEW.id; END""")
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS {table}_completion_update
            AFTER UPDATE OF completed ON {table} WHEN NEW.completed != OLD.completed BEGIN
            UPDATE {table} SET completed_at=CASE WHEN NEW.completed=1
                THEN strftime('%Y-%m-%dT%H:%M:%f+00:00','now') ELSE NULL END WHERE id=NEW.id; END""")
    for table in ('study_attempts', 'study_reviews'):
        connection.exec_driver_sql(f'CREATE INDEX IF NOT EXISTS ix_{table}_owner_project_created ON {table}(owner_id,project_id,created_at)')
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_time_owner_project_end ON time_entries(owner_id,project_id,ended_at)')
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_focus_owner_project_end ON focus_sessions(owner_id,project_id,ended_at)')

MIGRATIONS[10] = analytics_foundation


def dataset_foundation(connection, timestamp):
    # Metadata.create_all registers additive tables in the same backed-up transaction.
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_datasets_owner_project ON datasets(owner_id,project_id,created_at)')

MIGRATIONS[11] = dataset_foundation


def data_report_foundation(connection, timestamp):
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_data_reports_owner_project ON data_reports(owner_id,project_id,updated_at)')

MIGRATIONS[12] = data_report_foundation


def ux_foundation(connection, timestamp):
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_notes_project_pinned ON project_notes(project_id,pinned,updated_at)')


MIGRATIONS[13] = ux_foundation


def canvas_foundation(connection, timestamp):
    # create_all creates only new tables; legacy projects need this candidate key
    # for the composite board/project/workspace/owner foreign key.
    connection.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_canvas_scope ON projects(id,workspace_id,owner_id)')
    connection.exec_driver_sql('''CREATE TRIGGER IF NOT EXISTS canvas_scene_no_update
        BEFORE UPDATE ON canvas_scene_revisions BEGIN
        SELECT RAISE(ABORT, 'Scene revisions are immutable'); END''')
    # Parent deletion may cascade; direct removal of retained history may not.
    connection.exec_driver_sql('''CREATE TRIGGER IF NOT EXISTS canvas_scene_no_delete
        BEFORE DELETE ON canvas_scene_revisions
        WHEN EXISTS (SELECT 1 FROM canvas_boards WHERE id=OLD.board_id) BEGIN
        SELECT RAISE(ABORT, 'Scene revisions are immutable'); END''')


MIGRATIONS[14] = canvas_foundation


def canvas_generation_foundation(connection, timestamp):
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_canvas_artifacts_board_owner ON canvas_artifacts(board_id,owner_id)')
    connection.exec_driver_sql('''CREATE TRIGGER IF NOT EXISTS canvas_artifact_version_no_update
        BEFORE UPDATE ON canvas_artifact_versions BEGIN
        SELECT RAISE(ABORT, 'Artifact versions are immutable'); END''')
    connection.exec_driver_sql('''CREATE TRIGGER IF NOT EXISTS canvas_artifact_version_no_delete
        BEFORE DELETE ON canvas_artifact_versions
        WHEN EXISTS (SELECT 1 FROM canvas_artifacts WHERE id=OLD.artifact_id) BEGIN
        SELECT RAISE(ABORT, 'Artifact versions are immutable'); END''')


MIGRATIONS[15] = canvas_generation_foundation


def canvas_chat_navigation(connection, timestamp):
    columns = {r[1] for r in connection.exec_driver_sql('PRAGMA table_info(canvas_generation_jobs)')}
    if 'conversation_id' not in columns:
        connection.exec_driver_sql('ALTER TABLE canvas_generation_jobs ADD COLUMN conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL')
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_canvas_jobs_conversation ON canvas_generation_jobs(board_id,conversation_id,created_at)')


MIGRATIONS[16] = canvas_chat_navigation


def canvas_openui_format(connection, timestamp):
    columns = {r[1] for r in connection.exec_driver_sql('PRAGMA table_info(canvas_generation_jobs)')}
    if 'output_format' not in columns:
        connection.exec_driver_sql("ALTER TABLE canvas_generation_jobs ADD COLUMN output_format VARCHAR(24) NOT NULL DEFAULT 'kumuta-json-v1'")
    events = {r[1] for r in connection.exec_driver_sql('PRAGMA table_info(canvas_generation_events)')}
    if 'preview_json' not in events:
        connection.exec_driver_sql('ALTER TABLE canvas_generation_events ADD COLUMN preview_json TEXT')


MIGRATIONS[17] = canvas_openui_format


def canvas_openui_preview_repair(connection, timestamp):
    # Some running development instances recorded v17 before its streaming
    # column was added. An applied migration is never rerun by the runner.
    # Recheck both additive fields under a new version, preserving all rows.
    canvas_openui_format(connection, timestamp)


MIGRATIONS[18] = canvas_openui_preview_repair


def canvas_chat_composer(connection, timestamp):
    for name, definition in (
        ('user_message_id', 'INTEGER REFERENCES messages(id) ON DELETE SET NULL'),
        ('assistant_message_id', 'INTEGER REFERENCES messages(id) ON DELETE SET NULL'),
        ('reply_text', 'TEXT'),
    ):
        if name not in {r[1] for r in connection.exec_driver_sql('PRAGMA table_info(canvas_generation_jobs)')}:
            connection.exec_driver_sql(f'ALTER TABLE canvas_generation_jobs ADD COLUMN {name} {definition}')
    if 'canvas_generation_mode' not in {r[1] for r in connection.exec_driver_sql('PRAGMA table_info(users)')}:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN canvas_generation_mode VARCHAR(16) NOT NULL DEFAULT 'auto'")


MIGRATIONS[19] = canvas_chat_composer


def canvas_resource_foundation(connection, timestamp):
    # New association table is registered by create_all inside the backed-up transaction.
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_canvas_media_source ON canvas_board_media(kind,source_id)')

MIGRATIONS[20] = canvas_resource_foundation


def canvas_board_datasets(connection, timestamp):
    """Preserve dataset IDs, files and media links while adding private board scope.

    SQLite cannot relax NOT NULL with ALTER COLUMN. Copy both the dataset table
    and its FK-dependent associations inside the runner's backed-up transaction.
    Keep foreign keys enabled throughout, including rollback and integrity checks.
    """
    columns = {r[1]: r for r in connection.exec_driver_sql('PRAGMA table_info(datasets)')}
    if 'board_id' in columns and not columns['project_id'][3]:
        return
    from sqlalchemy.schema import CreateTable
    from .dataset_models import Dataset
    from .board_models import BoardMediaLink
    for table in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars().all():
        if table.startswith('sqlite_'):continue
        for fk in connection.exec_driver_sql(f'PRAGMA foreign_key_list("{table}")'):
            if fk[2]=='datasets' and table!='canvas_board_media':
                raise RuntimeError('Unexpected dataset dependency; board-scope migration rolled back.')
    objects=connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type IN ('index','trigger') AND tbl_name IN ('datasets','canvas_board_media') AND sql IS NOT NULL").scalars().all()
    seq=connection.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name='datasets'").scalar() or 0
    create=str(CreateTable(Dataset.__table__).compile(dialect=connection.dialect))
    create=create.replace('CREATE TABLE datasets','CREATE TABLE _kumuta_board_datasets',1)
    connection.exec_driver_sql(create)
    names=','.join('"'+c+'"' for c in columns)
    connection.exec_driver_sql(f'INSERT INTO _kumuta_board_datasets ({names}) SELECT {names} FROM datasets')
    media=str(CreateTable(BoardMediaLink.__table__).compile(dialect=connection.dialect)).replace('CREATE TABLE canvas_board_media','CREATE TABLE _kumuta_board_media',1).replace('REFERENCES datasets','REFERENCES _kumuta_board_datasets')
    connection.exec_driver_sql(media)
    connection.exec_driver_sql('INSERT INTO _kumuta_board_media SELECT * FROM canvas_board_media')
    connection.exec_driver_sql('DROP TABLE canvas_board_media')
    connection.exec_driver_sql('DROP TABLE datasets')
    connection.exec_driver_sql('ALTER TABLE _kumuta_board_datasets RENAME TO datasets')
    connection.exec_driver_sql('ALTER TABLE _kumuta_board_media RENAME TO canvas_board_media')
    for sql in objects:connection.exec_driver_sql(sql)
    connection.execute(text("INSERT INTO sqlite_sequence(name,seq) SELECT 'datasets',:seq WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='datasets')"),{'seq':seq})
    connection.execute(text('UPDATE sqlite_sequence SET seq=max(seq,:seq) WHERE name=\'datasets\''),{'seq':seq})
    if connection.exec_driver_sql('PRAGMA foreign_key_check').all():
        raise RuntimeError('Dataset scope integrity check failed; migration rolled back.')


MIGRATIONS[21] = canvas_board_datasets


def canvas_sharing_sessions(connection, timestamp):
    # Tables are created by create_all in the same backed-up migration transaction.
    connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_canvas_members_user ON canvas_board_members(user_id,status,board_id)')


MIGRATIONS[22] = canvas_sharing_sessions


def shared_chat_capabilities(connection, timestamp):
    columns = {r[1] for r in connection.exec_driver_sql('PRAGMA table_info(quickui_responses)')}
    for name, definition in (('interaction_state', "TEXT NOT NULL DEFAULT '{}'"), ('state_revision', 'INTEGER NOT NULL DEFAULT 0')):
        if name not in columns:
            connection.exec_driver_sql(f'ALTER TABLE quickui_responses ADD COLUMN {name} {definition}')
    columns = [r[1] for r in connection.exec_driver_sql('PRAGMA table_info(datasets)')]
    if 'conversation_id' in columns:
        return
    # Rebuild only the scoped ledger and its existing FK association. Preserve
    # source files, IDs, sequences, indexes and triggers under the runner's backup.
    from sqlalchemy.schema import CreateTable
    from .dataset_models import Dataset
    from .board_models import BoardMediaLink
    for table in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars().all():
        if table.startswith('sqlite_'): continue
        for fk in connection.exec_driver_sql(f'PRAGMA foreign_key_list("{table}")'):
            if fk[2] == 'datasets' and table != 'canvas_board_media':
                raise RuntimeError('Unexpected dataset dependency; chat-scope migration rolled back.')
    objects = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type IN ('index','trigger') AND tbl_name IN ('datasets','canvas_board_media') AND sql IS NOT NULL").scalars().all()
    seq = connection.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name='datasets'").scalar() or 0
    create = str(CreateTable(Dataset.__table__).compile(dialect=connection.dialect)).replace('CREATE TABLE datasets', 'CREATE TABLE _kumuta_chat_datasets', 1)
    connection.exec_driver_sql(create)
    names = ','.join('"'+c+'"' for c in columns)
    connection.exec_driver_sql(f'INSERT INTO _kumuta_chat_datasets ({names}) SELECT {names} FROM datasets')
    media = str(CreateTable(BoardMediaLink.__table__).compile(dialect=connection.dialect)).replace('CREATE TABLE canvas_board_media', 'CREATE TABLE _kumuta_chat_media', 1).replace('REFERENCES datasets', 'REFERENCES _kumuta_chat_datasets')
    connection.exec_driver_sql(media)
    connection.exec_driver_sql('INSERT INTO _kumuta_chat_media SELECT * FROM canvas_board_media')
    connection.exec_driver_sql('DROP TABLE canvas_board_media')
    connection.exec_driver_sql('DROP TABLE datasets')
    connection.exec_driver_sql('ALTER TABLE _kumuta_chat_datasets RENAME TO datasets')
    connection.exec_driver_sql('ALTER TABLE _kumuta_chat_media RENAME TO canvas_board_media')
    for sql in objects: connection.exec_driver_sql(sql)
    connection.execute(text("INSERT INTO sqlite_sequence(name,seq) SELECT 'datasets',:seq WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='datasets')"), {'seq': seq})
    connection.execute(text("UPDATE sqlite_sequence SET seq=max(seq,:seq) WHERE name='datasets'"), {'seq': seq})
    if connection.exec_driver_sql('PRAGMA foreign_key_check').all():
        raise RuntimeError('Chat dataset integrity check failed; migration rolled back.')


MIGRATIONS[23] = shared_chat_capabilities
