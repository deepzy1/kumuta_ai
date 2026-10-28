"""Authenticated local SaaS operations. No Gemini imports or calls."""
from datetime import date
from typing import Literal

from fastapi import Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from .database import Conversation, User, now
from .workspace_models import ChecklistItem, Note, Project, Task, TaskColumn, TaskDocument, Workspace
from . import workspace_schemas as schema
from . import workspaces as service


def register(app, user_dependency, db_dependency, owned_conversation, unlocked):
    def project_for_write(pid, user, db):
        service.lock_writes(user, db)
        return service.owned_project(pid, user, db, writable=True)

    def verify_delete(row, data):
        service.check_revision(row, data.revision)
        if row.name != data.confirm_name:
            raise HTTPException(422, 'Enter the current name to confirm deletion.')

    def detach_conversations(project_ids, user, db):
        # Refuse to detach context while a reply is being generated.
        for conversation in db.scalars(select(Conversation).where(Conversation.project_id.in_(project_ids))):
            if conversation.user_id != user.id:
                raise HTTPException(409, 'Project has an inconsistent conversation owner.')
            unlocked(conversation)
        db.execute(update(Conversation).where(Conversation.project_id.in_(project_ids)).values(project_id=None))

    @app.get('/workspaces')
    def list_workspaces(q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100),
                        offset: int = Query(0, ge=0), user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        query = select(Workspace).where(Workspace.owner_id == user.id)
        if q.strip():
            query = query.where(Workspace.name.icontains(q.strip(), autoescape=True))
        rows = list(db.scalars(query.order_by(Workspace.personal_owner_id.is_(None), Workspace.name, Workspace.id).offset(offset).limit(limit + 1)))
        return service.page(rows, limit, service.workspace_json)

    @app.post('/workspaces', status_code=201)
    def create_workspace(data: schema.WorkspaceCreate, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.lock_writes(user, db)
        row = service.create_workspace(user.id, data.name, db)
        db.commit()
        return service.workspace_json(row)

    @app.patch('/workspaces/{wid}')
    def edit_workspace(wid: int, data: schema.WorkspaceEdit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.lock_writes(user, db)
        row = service.owned_workspace(wid, user, db)
        service.check_revision(row, data.revision)
        row.name = data.name
        service.touch(row)
        db.commit()
        return service.workspace_json(row)

    @app.delete('/workspaces/{wid}')
    def delete_workspace(wid: int, data: schema.ConfirmDelete, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.lock_writes(user, db)
        row = service.owned_workspace(wid, user, db)
        verify_delete(row, data)
        if row.personal_owner_id is not None:
            raise HTTPException(409, 'Your personal workspace cannot be deleted.')
        ids = list(db.scalars(select(Project.id).where(Project.workspace_id == wid)))
        detach_conversations(ids, user, db)
        db.delete(row)
        db.commit()
        return {'ok': True, 'conversations_preserved': True}

    @app.get('/workspaces/{wid}/projects')
    def list_projects(wid: int, q: str = Query('', max_length=120), archived: bool = False,
                      sort: Literal['updated', 'name', 'created'] = 'updated', limit: int = Query(40, ge=1, le=100),
                      offset: int = Query(0, ge=0), user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.owned_workspace(wid, user, db)
        query = select(Project).where(Project.workspace_id == wid, Project.owner_id == user.id, Project.archived == archived)
        if q.strip():
            query = query.where(or_(Project.name.icontains(q.strip(), autoescape=True), Project.description.icontains(q.strip(), autoescape=True)))
        order = {'updated': Project.updated_at.desc(), 'name': Project.name, 'created': Project.created_at.desc()}[sort]
        rows = list(db.scalars(query.order_by(order, Project.id).offset(offset).limit(limit + 1)))
        return service.page(rows, limit, service.project_json)

    @app.post('/workspaces/{wid}/projects', status_code=201)
    def create_project(wid: int, data: schema.ProjectCreate, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.lock_writes(user, db)
        row = service.create_project(service.owned_workspace(wid, user, db), data, db)
        db.commit()
        return service.project_json(row)

    @app.get('/projects/{pid}')
    def get_project(pid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        row = service.owned_project(pid, user, db)
        return {**service.project_json(row), 'overview': service.project_overview(row, db)}

    @app.patch('/projects/{pid}')
    def edit_project(pid: int, data: schema.ProjectEdit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.lock_writes(user, db)
        row = service.owned_project(pid, user, db)
        service.check_revision(row, data.revision)
        for key, value in data.model_dump(exclude={'revision'}, exclude_unset=True).items():
            setattr(row, key, value)
        service.touch(row)
        db.commit()
        return service.project_json(row)

    @app.delete('/projects/{pid}')
    def delete_project(pid: int, data: schema.ConfirmDelete, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.lock_writes(user, db)
        row = service.owned_project(pid, user, db)
        verify_delete(row, data)
        detach_conversations([pid], user, db)
        db.delete(row)
        db.commit()
        return {'ok': True, 'conversations_preserved': True}

    @app.get('/projects/{pid}/columns')
    def columns(pid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = service.owned_project(pid, user, db)
        return {'items': [service.column_json(row) for row in db.scalars(select(TaskColumn).where(TaskColumn.project_id == pid)
                            .order_by(TaskColumn.position, TaskColumn.id))], 'board_revision': project.board_revision}

    @app.post('/projects/{pid}/columns', status_code=201)
    def create_column(pid: int, data: schema.ColumnCreate, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        service.check_revision(project, data.board_revision, 'board_revision')
        if db.scalar(select(func.count()).select_from(TaskColumn).where(TaskColumn.project_id == pid)) >= 40:
            raise HTTPException(422, 'A project supports up to 40 columns.')
        row = TaskColumn(project_id=pid, name=data.name, is_done=data.is_done,
                         position=service.next_position(TaskColumn, [TaskColumn.project_id == pid], db))
        db.add(row)
        service.touch_board(project)
        db.commit()
        return {'column': service.column_json(row), 'board_revision': project.board_revision}

    @app.patch('/projects/{pid}/columns/{column_id}')
    def edit_column(pid: int, column_id: int, data: schema.ColumnEdit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        service.check_revision(project, data.board_revision, 'board_revision')
        row = service.child(TaskColumn, column_id, project, db)
        if data.name is not None:
            row.name = data.name
        if data.is_done is not None and row.is_done != data.is_done:
            db.execute(update(Task).where(Task.project_id == pid, Task.column_id == column_id).values(
                completed=data.is_done, revision=Task.revision + 1, updated_at=now()))
            row.is_done = data.is_done
        service.touch_board(project)
        db.commit()
        return {'column': service.column_json(row), 'board_revision': project.board_revision}

    @app.post('/projects/{pid}/columns/{column_id}/move')
    def move_column(pid: int, column_id: int, data: schema.Move, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        service.check_revision(project, data.board_revision, 'board_revision')
        row = service.child(TaskColumn, column_id, project, db)
        service.place(TaskColumn, row, [TaskColumn.project_id == pid], data.before_id, db)
        service.touch_board(project)
        db.commit()
        return {'column': service.column_json(row), 'board_revision': project.board_revision}

    @app.delete('/projects/{pid}/columns/{column_id}')
    def delete_column(pid: int, column_id: int, data: schema.ColumnDelete, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        service.check_revision(project, data.board_revision, 'board_revision')
        row = service.child(TaskColumn, column_id, project, db)
        if db.scalar(select(func.count()).select_from(TaskColumn).where(TaskColumn.project_id == pid)) <= 1:
            raise HTTPException(409, 'Keep at least one task column.')
        tasks = list(db.scalars(select(Task).where(Task.project_id == pid, Task.column_id == column_id).order_by(Task.position, Task.id)))
        if tasks and (data.destination_id is None or data.destination_id == column_id):
            raise HTTPException(422, 'Choose another column for existing tasks.')
        if data.destination_id is not None:
            if data.destination_id == column_id:
                raise HTTPException(422, 'Choose another column.')
            destination = service.child(TaskColumn, data.destination_id, project, db)
            position = service.next_position(Task, [Task.project_id == pid, Task.column_id == destination.id], db)
            for task in tasks:
                task.column_id, task.completed, task.position = destination.id, destination.is_done, position
                position += service.STEP
                service.touch(task)
        db.flush()
        db.delete(row)
        service.touch_board(project)
        db.commit()
        return {'ok': True, 'board_revision': project.board_revision}

    @app.get('/projects/{pid}/tasks')
    def list_tasks(pid: int, q: str = Query('', max_length=200), column_id: int | None = None,
                   parent_id: int | None = None, roots_only: bool = False, completed: bool | None = None,
                   priority: schema.Priority | None = None, due_before: date | None = None,
                   sort: Literal['position', 'due', 'priority', 'updated', 'title'] = 'position',
                   limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                   user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = service.owned_project(pid, user, db)
        query = select(Task).where(Task.project_id == pid)
        if column_id is not None:
            service.child(TaskColumn, column_id, project, db)
            query = query.where(Task.column_id == column_id)
        if parent_id is not None:
            service.child(Task, parent_id, project, db)
            query = query.where(Task.parent_id == parent_id)
        elif roots_only:
            query = query.where(Task.parent_id.is_(None))
        if q.strip():
            query = query.where(or_(Task.title.icontains(q.strip(), autoescape=True), Task.description.icontains(q.strip(), autoescape=True)))
        if completed is not None:
            query = query.where(Task.completed == completed)
        if priority is not None:
            query = query.where(Task.priority == priority)
        if due_before is not None:
            query = query.where(Task.due_date <= due_before.isoformat())
        from sqlalchemy import case
        order = {'position': [Task.position], 'due': [Task.due_date.is_(None), Task.due_date],
                 'priority': [case({'urgent': 0, 'high': 1, 'medium': 2, 'low': 3, 'none': 4}, value=Task.priority)],
                 'updated': [Task.updated_at.desc()], 'title': [Task.title]}[sort]
        rows = list(db.scalars(query.order_by(*order, Task.id).offset(offset).limit(limit + 1)))
        return {'items': service.task_views(rows[:limit], db), 'has_more': len(rows) > limit, 'board_revision': project.board_revision}

    @app.post('/projects/{pid}/tasks', status_code=201)
    def create_task(pid: int, data: schema.TaskCreate, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        column = service.child(TaskColumn, data.column_id, project, db)
        if data.parent_id is not None:
            parent = service.child(Task, data.parent_id, project, db)
            if parent.parent_id is not None:
                raise HTTPException(422, 'Only one level of subtasks is supported.')
        values = data.model_dump(exclude={'due_date'})
        row = Task(project_id=pid, created_by=user.id, **values, completed=column.is_done,
                   due_date=data.due_date.isoformat() if data.due_date else None,
                   position=service.next_position(Task, [Task.project_id == pid, Task.column_id == column.id], db))
        db.add(row)
        service.touch_board(project)
        db.commit()
        return {'task': service.task_views([row], db)[0], 'board_revision': project.board_revision}

    @app.get('/projects/{pid}/tasks/{tid}')
    def get_task(pid: int, tid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = service.owned_project(pid, user, db)
        return service.task_views([service.child(Task, tid, project, db)], db)[0]

    @app.patch('/projects/{pid}/tasks/{tid}')
    def edit_task(pid: int, tid: int, data: schema.TaskEdit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        row = service.child(Task, tid, project, db)
        service.check_revision(row, data.revision)
        if 'document_ids' in data.model_fields_set:
            from . import documents
            from .document_models import Document
            keys = documents.keys_for(user, db, project_id=pid)
            ids = set(data.document_ids)
            allowed = set(db.scalars(select(Document.id).where(Document.id.in_(ids), Document.user_id == user.id, Document.scope_key.in_(keys))))
            if ids != allowed:
                raise HTTPException(404, 'Project document not found')
            db.execute(delete(TaskDocument).where(TaskDocument.task_id == tid))
            db.add_all([TaskDocument(task_id=tid, document_id=did) for did in ids])
        for key, value in data.model_dump(exclude_unset=True, exclude={'revision', 'checklist', 'document_ids'}).items():
            setattr(row, key, value.isoformat() if key == 'due_date' and value else value)
        if data.checklist is not None:
            db.execute(delete(ChecklistItem).where(ChecklistItem.task_id == tid))
            db.add_all([ChecklistItem(task_id=tid, position=i, **item.model_dump()) for i, item in enumerate(data.checklist)])
        service.touch(row)
        service.touch_board(project)
        db.commit()
        return {'task': service.task_views([row], db)[0], 'board_revision': project.board_revision}

    @app.post('/projects/{pid}/tasks/{tid}/move')
    def move_task(pid: int, tid: int, data: schema.TaskMove, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        service.check_revision(project, data.board_revision, 'board_revision')
        row = service.child(Task, tid, project, db)
        column = service.child(TaskColumn, data.column_id, project, db)
        service.place(Task, row, [Task.project_id == pid, Task.column_id == column.id], data.before_id, db)
        row.column_id, row.completed = column.id, column.is_done
        service.touch(row)
        service.touch_board(project)
        db.commit()
        return {'task': service.task_views([row], db)[0], 'board_revision': project.board_revision}

    @app.delete('/projects/{pid}/tasks/{tid}')
    def delete_task(pid: int, tid: int, data: schema.Revision, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        row = service.child(Task, tid, project, db)
        service.check_revision(row, data.revision)
        db.delete(row)
        service.touch_board(project)
        db.commit()
        return {'ok': True, 'board_revision': project.board_revision}

    @app.get('/projects/{pid}/notes')
    def list_notes(pid: int, q: str = Query('', max_length=200), limit: int = Query(40, ge=1, le=100),
                   offset: int = Query(0, ge=0), user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.owned_project(pid, user, db)
        query = select(Note).where(Note.project_id == pid)
        if q.strip():
            query = query.where(or_(Note.title.icontains(q.strip(), autoescape=True), Note.content.icontains(q.strip(), autoescape=True)))
        rows = list(db.scalars(query.order_by(Note.pinned.desc(), Note.updated_at.desc(), Note.id.desc()).offset(offset).limit(limit + 1)))
        return service.page(rows, limit, lambda row: service.note_json(row, include_content=False))

    @app.post('/projects/{pid}/notes', status_code=201)
    def create_note(pid: int, data: schema.NoteCreate, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project_for_write(pid, user, db)
        row = Note(project_id=pid, **data.model_dump())
        db.add(row)
        db.commit()
        return service.note_json(row)

    @app.get('/projects/{pid}/notes/{nid}')
    def get_note(pid: int, nid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = service.owned_project(pid, user, db)
        return service.note_json(service.child(Note, nid, project, db))

    @app.put('/projects/{pid}/notes/{nid}')
    def edit_note(pid: int, nid: int, data: schema.NoteEdit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        row = service.child(Note, nid, project, db)
        service.check_revision(row, data.revision)
        row.title, row.content = data.title, data.content
        if 'pinned' in data.model_fields_set: row.pinned = data.pinned
        service.touch(row)
        db.commit()
        return service.note_json(row)

    @app.delete('/projects/{pid}/notes/{nid}')
    def delete_note(pid: int, nid: int, data: schema.Revision, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        project = project_for_write(pid, user, db)
        row = service.child(Note, nid, project, db)
        service.check_revision(row, data.revision)
        db.delete(row)
        db.commit()
        return {'ok': True}

    @app.patch('/conversations/{cid}/project')
    def move_conversation(cid: int, data: schema.ConversationProject, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.lock_writes(user, db)
        row = owned_conversation(cid, user, db)
        unlocked(row)
        from .board_models import BoardConversation
        if data.project_id != row.project_id and db.scalar(select(BoardConversation).where(BoardConversation.conversation_id == cid)):
            raise HTTPException(409, 'Unlink this conversation from its board before moving it.')
        if row.project_id != data.expected_project_id:
            raise HTTPException(409, 'Conversation moved elsewhere. Reload it and try again.')
        if row.project_id is not None:
            service.owned_project(row.project_id, user, db)
        if data.project_id is not None:
            service.owned_project(data.project_id, user, db, writable=True)
        row.project_id, row.updated_at = data.project_id, now()
        db.commit()
        return {'id': row.id, 'project_id': row.project_id, 'updated_at': row.updated_at}
