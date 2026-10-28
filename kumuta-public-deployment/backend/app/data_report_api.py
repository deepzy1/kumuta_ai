"""Authenticated saved report CRUD/refresh and formula-safe exports."""
import json
from typing import Literal
from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .database import User
from .dataset_api import ConfirmDelete
from .report_models import DataReport
from . import data_reports as service, workspaces, datasets


def register(app, user_dependency, db_dependency):
    base = '/projects/{pid}/data/reports'

    @app.get(base)
    def listing(pid: int, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0, le=100000), user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.owned_project(pid, user, db)
        rows = list(db.scalars(select(DataReport).where(DataReport.owner_id == user.id, DataReport.project_id == pid).order_by(DataReport.updated_at.desc(), DataReport.id.desc()).offset(offset).limit(limit+1)))
        return {'items': [service.view(r) for r in rows[:limit]], 'has_more': len(rows)>limit, 'ai_calls': 0}

    @app.post(base, status_code=201)
    def create(pid: int, data: service.ReportData, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.owned_project(pid, user, db, writable=True)
        widgets = service.validate_widgets(pid, data.widgets, user, db)
        db.commit()  # Expensive parsing/calculation happens outside write reservations.
        workspaces.lock_writes(user, db); workspaces.owned_project(pid, user, db, writable=True)
        for widget in data.widgets: datasets.owned(pid, widget.dataset_id, user, db)
        if db.scalar(select(func.count()).select_from(DataReport).where(DataReport.owner_id == user.id, DataReport.project_id == pid)) >= 100:
            raise HTTPException(413, 'Use at most 100 reports per project.')
        row = DataReport(owner_id=user.id, project_id=pid, name=data.name, description=data.description, configuration=json.dumps(widgets))
        db.add(row); db.commit(); return service.view(row)

    @app.get(base + '/{rid}')
    def detail(pid: int, rid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        return service.view(service.owned(pid, rid, user, db))

    @app.put(base + '/{rid}')
    def edit(pid: int, rid: int, data: service.ReportEdit, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        service.owned(pid, rid, user, db, writable=True)
        widgets = service.validate_widgets(pid, data.widgets, user, db); db.commit()
        workspaces.lock_writes(user, db)
        row = service.owned(pid, rid, user, db, writable=True); workspaces.check_revision(row, data.revision)
        for widget in data.widgets: datasets.owned(pid, widget.dataset_id, user, db)
        row.name, row.description, row.configuration = data.name, data.description, json.dumps(widgets)
        workspaces.touch(row); db.commit(); return service.view(row)

    @app.post(base + '/{rid}/run')
    def run(pid: int, rid: int, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        row = service.owned(pid, rid, user, db)
        return service.run(pid, row, user, db)

    @app.get(base + '/{rid}/export')
    def export(pid: int, rid: int, format: Literal['csv', 'json'] = 'csv', user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        row = service.owned(pid, rid, user, db)
        output = service.run(pid, row, user, db, export_all=True)
        body = service.export_csv(output) if format == 'csv' else json.dumps(output, ensure_ascii=False)
        if len(body.encode()) > 16 * 1024 * 1024: raise HTTPException(413, 'Export exceeds 16 MB. Add report filters.')
        return Response(body, media_type='text/csv' if format == 'csv' else 'application/json', headers={
            'Content-Disposition': f'attachment; filename="kumuta-report-{rid}.{format}"', 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.delete(base + '/{rid}')
    def remove(pid: int, rid: int, data: ConfirmDelete, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        workspaces.lock_writes(user, db)
        row = service.owned(pid, rid, user, db); workspaces.check_revision(row, data.revision)
        db.delete(row); db.commit(); return {'ok': True, 'ai_calls': 0}
