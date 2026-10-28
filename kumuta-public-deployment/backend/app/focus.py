"""Timestamp-based session state and local goal/time calculations."""
import json
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import delete, select
from . import focus_models as m, workspaces as ws
from .database import now
from .progress import goal_progress
from .workspace_models import Task


def clock(): return datetime.now(timezone.utc)
def stamp(value): return value.astimezone(timezone.utc).isoformat()
def dt(value): return datetime.fromisoformat(value)


def owned(model, identity, user, db):
    row = db.scalar(select(model).where(model.id==identity,model.owner_id==user.id))
    if row is None: raise HTTPException(404,'Focus record not found')
    if row.project_id is not None: ws.owned_project(row.project_id,user,db)
    return row


def references(pid, tid, user, db, write=True):
    if pid is not None:
        project=ws.owned_project(pid,user,db,writable=write)
        if tid is not None: ws.child(Task,tid,project,db)
    elif tid is not None: raise HTTPException(422,'A task requires its project.')


def elapsed(row, instant):
    seconds=row.elapsed_seconds
    if row.status=='running' and row.running_since: seconds+=max(0,(instant-dt(row.running_since)).total_seconds())
    return min(seconds,row.planned_seconds) if row.planned_seconds else seconds


def view(row, instant=None):
    data={c.name:getattr(row,c.name) for c in row.__table__.columns if c.name != 'segments'}
    if isinstance(row,m.Session):
        instant=instant or clock();data['elapsed_seconds']=elapsed(row,instant)
        data['remaining_seconds']=max(0,row.planned_seconds-data['elapsed_seconds']) if row.planned_seconds else None
        data['server_now']=stamp(instant)
    return data


def segment(row, instant):
    if row.status=='running' and row.running_since:
        segments=json.loads(row.segments)
        segments.append([row.running_since, stamp(instant)])
        row.segments=json.dumps(segments)


def close(row, instant, db, status):
    seconds=elapsed(row,instant)
    segment(row,instant)
    row.elapsed_seconds=seconds;row.ended_at=stamp(instant);row.running_since=None;row.status=status;row.revision+=1
    if row.kind in ('focus','tracking') and seconds>0:
        db.add(m.TimeEntry(owner_id=row.owner_id,project_id=row.project_id,task_id=row.task_id,session_id=row.id,
            started_at=row.started_at,ended_at=row.ended_at,duration_seconds=seconds,notes=row.notes,segments=row.segments,
            allocation_estimated=abs(sum((dt(b)-dt(a)).total_seconds() for a,b in json.loads(row.segments))-seconds)>.01))


def settle(user, db, instant=None):
    # Caller holds the existing serialized write reservation.
    instant=instant or clock()
    row=db.scalar(select(m.Session).where(m.Session.owner_id==user.id,m.Session.status.in_(['running','paused'])))
    if row and row.status=='running' and row.planned_seconds and elapsed(row,instant)>=row.planned_seconds:
        end=dt(row.running_since)+timedelta(seconds=max(0,row.planned_seconds-row.elapsed_seconds))
        close(row,end,db,'completed');db.flush();return None
    return row


def overlap(start, end, user, db, excluded=None):
    query=select(m.TimeEntry).where(m.TimeEntry.owner_id==user.id,m.TimeEntry.started_at<end,m.TimeEntry.ended_at>start)
    if excluded is not None:query=query.where(m.TimeEntry.id!=excluded)
    if db.scalar(query.limit(1)) is not None:raise HTTPException(409,'Time entry overlaps recorded work.')
    active=db.scalar(select(m.Session).where(m.Session.owner_id==user.id,m.Session.status.in_(['running','paused'])))
    if active and end>active.started_at:raise HTTPException(409,'Time entry overlaps an active session. Stop it first.')


def goal_view(row,db):
    data=view(row);data['milestones']=json.loads(row.milestones)
    data['task_ids']=list(db.scalars(select(m.GoalTask.task_id).where(m.GoalTask.goal_id==row.id)))
    tasks=list(db.scalars(select(Task).where(Task.id.in_(data['task_ids']))))
    data['progress']=goal_progress(data['milestones'], [x.completed for x in tasks], row.status)
    return data


def apply_goal(row,data,user,db):
    values=data.model_dump(mode='json',exclude={'revision'})
    for tid in values['task_ids']:references(row.project_id,tid,user,db)
    for key,value in values.items():
        if key!='task_ids':setattr(row,key,json.dumps(value) if key=='milestones' else value)
    db.add(row);db.flush();db.execute(delete(m.GoalTask).where(m.GoalTask.goal_id==row.id))
    db.add_all(m.GoalTask(goal_id=row.id,task_id=tid) for tid in set(values['task_ids']))
