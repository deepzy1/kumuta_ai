"""No Gemini imports: goals, durable timers and time entries are ordinary SaaS."""
import json
from datetime import timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from . import focus as s, focus_models as m, focus_schemas as schema, workspaces as ws
from .database import User
from .time_accounting import allocate
from .study_schemas import Revision


def register(app,auth,session):
    def write(user,db):ws.lock_writes(user,db)
    def goal(pid,identity,user,db,writing=False):
        ws.owned_project(pid,user,db,writable=writing)
        row=s.owned(m.Goal,identity,user,db)
        if row.project_id!=pid:raise HTTPException(404,'Goal not found in this project')
        return row

    @app.get('/projects/{pid}/focus/goals')
    def goals(pid:int, limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),user:User=Depends(auth),db:DBSession=Depends(session)):
        ws.owned_project(pid,user,db)
        rows=list(db.scalars(select(m.Goal).where(m.Goal.project_id==pid,m.Goal.owner_id==user.id).order_by(m.Goal.id).offset(offset).limit(limit+1)))
        return {'items':[s.goal_view(x,db) for x in rows[:limit]],'has_more':len(rows)>limit}

    @app.post('/projects/{pid}/focus/goals',status_code=201)
    def create_goal(pid:int,data:schema.GoalData,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);ws.owned_project(pid,user,db,writable=True)
        row=m.Goal(owner_id=user.id,project_id=pid);s.apply_goal(row,data,user,db);db.commit();return s.goal_view(row,db)

    @app.get('/projects/{pid}/focus/goals/{identity}')
    def get_goal(pid:int,identity:int,user:User=Depends(auth),db:DBSession=Depends(session)):
        return s.goal_view(goal(pid,identity,user,db),db)

    @app.put('/projects/{pid}/focus/goals/{identity}')
    def edit_goal(pid:int,identity:int,data:schema.GoalEdit,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);row=goal(pid,identity,user,db,True);ws.check_revision(row,data.revision)
        s.apply_goal(row,data,user,db);ws.touch(row);db.commit();return s.goal_view(row,db)

    @app.delete('/projects/{pid}/focus/goals/{identity}')
    def delete_goal(pid:int,identity:int,data:Revision,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);row=goal(pid,identity,user,db,True);ws.check_revision(row,data.revision);db.delete(row);db.commit();return {'ok':True}

    @app.get('/focus/active')
    def active(user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);instant=s.clock();row=s.settle(user,db,instant);db.commit()
        return {'session':s.view(row,instant) if row else None,'server_now':s.stamp(instant)}

    @app.get('/focus/sessions')
    def sessions(project_id:int|None=None,limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),user:User=Depends(auth),db:DBSession=Depends(session)):
        if project_id is not None:ws.owned_project(project_id,user,db)
        write(user,db);s.settle(user,db);db.commit()
        query=select(m.Session).where(m.Session.owner_id==user.id)
        if project_id is not None:query=query.where(m.Session.project_id==project_id)
        rows=list(db.scalars(query.order_by(m.Session.id.desc()).offset(offset).limit(limit+1)))
        return {'items':[s.view(x) for x in rows[:limit]],'has_more':len(rows)>limit}

    @app.post('/focus/sessions',status_code=201)
    def start(data:schema.Start,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);instant=s.clock();active=s.settle(user,db,instant)
        if active:raise HTTPException(409,'You already have an active focus or tracking session. Stop it first.')
        s.references(data.project_id,data.task_id,user,db)
        stamp=s.stamp(instant)
        row=m.Session(owner_id=user.id,**data.model_dump(),started_at=stamp,running_since=stamp)
        # Existing entries must not claim future work over this new start.
        db.add(row);db.commit();return s.view(row,instant)

    @app.get('/focus/sessions/{identity}')
    def get_session(identity:int,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);row=s.owned(m.Session,identity,user,db);s.settle(user,db);db.commit();return s.view(row)

    @app.post('/focus/sessions/{identity}/{action}')
    def transition(identity:int,action:Literal['pause','resume','stop','complete'],data:Revision,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);row=s.owned(m.Session,identity,user,db);instant=s.clock();s.settle(user,db,instant)
        # Natural completion is committed even when a stale client requests pause.
        if row.status=='completed':db.commit();return s.view(row,instant)
        ws.check_revision(row,data.revision)
        if row.status not in ('running','paused'):raise HTTPException(409,'Session has already ended.')
        if action=='pause':
            if row.status!='running':raise HTTPException(409,'Session is already paused.')
            s.segment(row,instant);row.elapsed_seconds=s.elapsed(row,instant);row.running_since=None;row.status='paused';row.revision+=1
        elif action=='resume':
            if row.status!='paused':raise HTTPException(409,'Session is already running.')
            row.running_since=s.stamp(instant);row.status='running';row.revision+=1
        elif action=='stop':s.close(row,instant,db,'stopped')
        else:raise HTTPException(409,'The timer has not reached its duration. Stop it to finish early.')
        db.commit();return s.view(row,instant)

    @app.get('/focus/preferences')
    def preferences(user:User=Depends(auth),db:DBSession=Depends(session)):
        row=db.get(m.Preference,user.id)
        return s.view(row) if row else {'focus_seconds':1500,'short_break_seconds':300,'long_break_seconds':900,'revision':0}

    @app.put('/focus/preferences')
    def save_preferences(data:schema.Preferences,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);row=db.get(m.Preference,user.id)
        if (row.revision if row else 0)!=data.revision:raise HTTPException(409,'Timer preferences changed. Reload.')
        if row is None:row=m.Preference(owner_id=user.id,revision=0);db.add(row)
        for k,v in data.model_dump(exclude={'revision'}).items():setattr(row,k,v)
        row.revision+=1;db.commit();return s.view(row)

    @app.get('/time/entries')
    def entries(project_id:int|None=None,limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),user:User=Depends(auth),db:DBSession=Depends(session)):
        if project_id is not None:ws.owned_project(project_id,user,db)
        write(user,db);s.settle(user,db);db.commit()
        query=select(m.TimeEntry).where(m.TimeEntry.owner_id==user.id)
        if project_id is not None:query=query.where(m.TimeEntry.project_id==project_id)
        rows=list(db.scalars(query.order_by(m.TimeEntry.started_at.desc(),m.TimeEntry.id.desc()).offset(offset).limit(limit+1)))
        return {'items':[s.view(x) for x in rows[:limit]],'has_more':len(rows)>limit}

    def save_entry(row,data,user,db):
        s.references(data.project_id,data.task_id,user,db)
        start,end=s.stamp(data.started_at),s.stamp(data.ended_at)
        s.overlap(start,end,user,db,row.id)
        for k,v in data.model_dump(exclude={'revision'}).items():setattr(row,k,s.stamp(v) if k in ('started_at','ended_at') else v)
        row.duration_seconds=(data.ended_at-data.started_at).total_seconds()
        row.segments=json.dumps([[start,end]])
        row.adjusted=row.session_id is not None
        row.allocation_estimated=False

    @app.post('/time/entries',status_code=201)
    def create_entry(data:schema.EntryData,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);s.settle(user,db);row=m.TimeEntry(owner_id=user.id)
        save_entry(row,data,user,db);db.add(row);db.commit();return s.view(row)

    @app.put('/time/entries/{identity}')
    def edit_entry(identity:int,data:schema.EntryEdit,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);s.settle(user,db);row=s.owned(m.TimeEntry,identity,user,db);ws.check_revision(row,data.revision)
        save_entry(row,data,user,db);row.revision+=1;db.commit();return s.view(row)

    @app.delete('/time/entries/{identity}')
    def delete_entry(identity:int,data:Revision,user:User=Depends(auth),db:DBSession=Depends(session)):
        write(user,db);row=s.owned(m.TimeEntry,identity,user,db);ws.check_revision(row,data.revision)
        db.delete(row);db.commit();return {'ok':True}

    @app.get('/time/totals')
    def totals(project_id:int|None=None,tz:str=Query('UTC',max_length=100),user:User=Depends(auth),db:DBSession=Depends(session)):
        tz={'Asia/Calcutta':'Asia/Kolkata','Asia/Katmandu':'Asia/Kathmandu'}.get(tz,tz)
        try:zone=ZoneInfo(tz)
        except (ZoneInfoNotFoundError,ValueError):raise HTTPException(422,'Unknown timezone') from None
        if project_id is not None:ws.owned_project(project_id,user,db)
        write(user,db);s.settle(user,db);db.commit()
        instant=s.clock().astimezone(zone);day=instant.replace(hour=0,minute=0,second=0,microsecond=0)
        week=day-timedelta(days=day.weekday());end=day+timedelta(days=1)
        query=select(m.TimeEntry).where(m.TimeEntry.owner_id==user.id,m.TimeEntry.ended_at>s.stamp(week),m.TimeEntry.started_at<s.stamp(end))
        if project_id is not None:query=query.where(m.TimeEntry.project_id==project_id)
        daily=weekly=0;estimated=False
        boundaries=[(week+timedelta(days=i)).astimezone(timezone.utc) for i in range((end.date()-week.date()).days+1)]
        for row in db.scalars(query):
            values, approximation=allocate(row,boundaries)
            estimated |= approximation
            daily+=values[-1];weekly+=sum(values)
        return {'daily_seconds':round(daily),'weekly_seconds':round(weekly),'timezone':tz,'allocation_estimated':estimated,'day':day.date().isoformat(),'week_start':week.date().isoformat()}
