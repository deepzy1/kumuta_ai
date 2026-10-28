"""Authenticated report and download routes. No AI dependencies."""
from datetime import date
from typing import Literal
from fastapi import Depends, Query, Response
from sqlalchemy.orm import Session
from . import analytics
from .database import User


def register(app, auth, session):
    def parameters(preset: Literal['today', '7d', '30d', 'custom'] = '30d', start: date | None = None,
                   end: date | None = None, tz: str = Query('UTC', max_length=100),
                   workspace_id: int | None = Query(None, ge=1), project_id: int | None = Query(None, ge=1),
                   course_id: int | None = Query(None, ge=1), limit: int = Query(50, ge=1, le=200),
                   offset: int = Query(0, ge=0, le=1000000)):
        return dict(preset=preset, start=start, end=end, tz=tz, workspace_id=workspace_id,
                    project_id=project_id, course_id=course_id, limit=limit, offset=offset)

    @app.get('/analytics')
    def report(response: Response, filters: dict = Depends(parameters), user: User = Depends(auth), db: Session = Depends(session)):
        response.headers['Cache-Control'] = 'no-store'
        return analytics.report(user, db, **filters)

    @app.get('/analytics/export')
    def export(kind: Literal['study', 'focus', 'workspace'] = 'workspace', filters: dict = Depends(parameters),
               user: User = Depends(auth), db: Session = Depends(session)):
        data = analytics.report(user, db, **filters)
        return Response(analytics.export_csv(data, kind), media_type='text/csv; charset=utf-8', headers={
            'Content-Disposition': f'attachment; filename="kumuta-{kind}-{data["range"]["start"]}.csv"',
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
