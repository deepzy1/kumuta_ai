"""Durable state, isolation, concurrency and exact time accounting."""
import asyncio
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from sqlalchemy import select, text
import test_api as f
import test_workspaces as w
from app import focus
from app.database import SessionLocal
from app.focus_models import Session, TimeEntry

class FocusTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=f.APITests.asyncSetUp
    asyncTearDown=f.APITests.asyncTearDown
    call=f.APITests.call
    ok=w.WorkspaceAPITests.ok
    project=w.WorkspaceAPITests.project
    task=w.WorkspaceAPITests.task

    async def start(self,**values):return await self.ok('POST','/focus/sessions',201,json=values)
    async def act(self,row,action,status=200):return await self.ok('POST',f'/focus/sessions/{row["id"]}/{action}',status,json={'revision':row['revision']})

    async def test_timestamp_timer_pause_resume_refresh_natural_completion(self):
        p,cols=await self.project();task=await self.task(p,cols[0]);t=datetime(2026,10,10,10,tzinfo=timezone.utc)
        with patch.object(focus,'clock',return_value=t):s=await self.start(project_id=p['id'],task_id=task['id'],planned_seconds=60)
        with patch.object(focus,'clock',return_value=t+timedelta(seconds=20)):
            refreshed=(await self.ok('GET','/focus/active'))['session'];self.assertEqual(refreshed['remaining_seconds'],40)
            paused=await self.act(s,'pause');self.assertEqual(paused['elapsed_seconds'],20)
        with patch.object(focus,'clock',return_value=t+timedelta(seconds=200)):
            self.assertEqual((await self.ok('GET','/focus/active'))['session']['remaining_seconds'],40)
            resumed=await self.act(paused,'resume')
            await self.act(paused,'resume',409)
        with patch.object(focus,'clock',return_value=t+timedelta(seconds=500)):
            self.assertIsNone((await self.ok('GET','/focus/active'))['session'])
            complete=await self.ok('GET',f'/focus/sessions/{s["id"]}')
            self.assertEqual(complete['status'],'completed');self.assertEqual(complete['ended_at'],(t+timedelta(seconds=240)).isoformat())
            entry=(await self.ok('GET','/time/entries'))['items'][0]
            self.assertEqual(entry['duration_seconds'],60)
            await self.act(resumed,'complete')
            self.assertEqual(len((await self.ok('GET','/time/entries'))['items']),1)
        self.assertEqual(f.FakeClient.calls,[])

    async def test_tracking_duplicate_timers_and_concurrent_start(self):
        t=datetime(2026,10,10,10,tzinfo=timezone.utc)
        with patch.object(focus,'clock',return_value=t):
            responses=await asyncio.gather(self.call('POST','/focus/sessions',json={'kind':'tracking'}),self.call('POST','/focus/sessions',json={'kind':'focus','planned_seconds':120}))
            self.assertEqual(sorted(x.status_code for x in responses),[201,409])
            row=next(x.json() for x in responses if x.status_code==201)
            await self.ok('POST','/focus/sessions',409,json={'kind':'tracking'})
        with patch.object(focus,'clock',return_value=t+timedelta(seconds=30)):
            stopped=await self.act(row,'stop');self.assertEqual(stopped['elapsed_seconds'],30)
            await self.act(stopped,'stop',409)
            tracking=await self.start(kind='tracking')
        with patch.object(focus,'clock',return_value=t+timedelta(seconds=45)):
            stopped=await self.act(tracking,'stop');self.assertEqual(stopped['elapsed_seconds'],15)
        self.assertEqual(f.FakeClient.calls,[])

    async def test_breaks_preferences_and_invalid_transitions(self):
        prefs=await self.ok('GET','/focus/preferences');self.assertEqual(prefs['revision'],0)
        saved=await self.ok('PUT','/focus/preferences',json={'revision':0,'focus_seconds':3000,'short_break_seconds':60,'long_break_seconds':600})
        self.assertEqual(saved['revision'],1)
        await self.ok('PUT','/focus/preferences',409,json={'revision':0})
        await self.ok('POST','/focus/sessions',422,json={'planned_seconds':0})
        await self.ok('POST','/focus/sessions',422,json={'kind':'bad'})
        row=await self.start(kind='short_break',planned_seconds=60)
        await self.act(row,'resume',409);await self.act(row,'complete',409)
        await self.act(row,'stop');self.assertEqual((await self.ok('GET','/time/entries'))['items'],[])

    async def test_manual_time_crud_overlap_validation_totals_and_adjustment(self):
        p,cols=await self.project();task=await self.task(p,cols[0]);t=datetime(2026,10,10,10,tzinfo=timezone.utc)
        data={'project_id':p['id'],'task_id':task['id'],'started_at':t.isoformat(),'ended_at':(t+timedelta(hours=1)).isoformat(),'notes':'Manual'}
        row=await self.ok('POST','/time/entries',201,json=data)
        await self.ok('POST','/time/entries',409,json=data)
        await self.ok('POST','/time/entries',422,json={**data,'ended_at':t.isoformat()})
        await self.ok('POST','/time/entries',422,json={**data,'started_at':'2026-10-10T10:00:00'})
        row=await self.ok('PUT',f'/time/entries/{row["id"]}',json={**data,'revision':1,'ended_at':(t+timedelta(hours=2)).isoformat()})
        with patch.object(focus,'clock',return_value=t+timedelta(hours=3)):
            totals=await self.ok('GET',f'/time/totals?project_id={p["id"]}&tz=Asia/Kolkata')
            self.assertEqual(totals['daily_seconds'],7200);self.assertEqual(totals['weekly_seconds'],7200)
            alias=await self.ok('GET',f'/time/totals?project_id={p["id"]}&tz=Asia/Calcutta')
            self.assertEqual(alias['daily_seconds'],7200);self.assertEqual(alias['timezone'],'Asia/Kolkata')
        await self.ok('GET','/time/totals?tz=Unknown',422)
        await self.ok('DELETE',f'/time/entries/{row["id"]}',json={'revision':2})
        with patch.object(focus,'clock',return_value=t):session=await self.start(kind='tracking',project_id=p['id'])
        await self.ok('POST','/time/entries',409,json=data)
        with patch.object(focus,'clock',return_value=t+timedelta(minutes=30)):await self.act(session,'stop')
        measured=(await self.ok('GET','/time/entries'))['items'][0]
        adjusted=await self.ok('PUT',f'/time/entries/{measured["id"]}',json={**data,'revision':1})
        self.assertTrue(adjusted['adjusted'])
        self.assertEqual((await self.ok('GET',f'/focus/sessions/{session["id"]}'))['elapsed_seconds'],1800)
        self.assertEqual(f.FakeClient.calls,[])

    async def test_paused_segments_across_midnight_have_exact_daily_totals(self):
        t=datetime(2026,10,10,23,50,tzinfo=timezone.utc)
        with patch.object(focus,'clock',return_value=t):row=await self.start(kind='tracking')
        with patch.object(focus,'clock',return_value=t+timedelta(minutes=5)):row=await self.act(row,'pause')
        with patch.object(focus,'clock',return_value=t+timedelta(minutes=30)):row=await self.act(row,'resume')
        with patch.object(focus,'clock',return_value=t+timedelta(minutes=35)):
            await self.act(row,'stop');totals=await self.ok('GET','/time/totals?tz=UTC')
            self.assertEqual(totals['daily_seconds'],300);self.assertEqual(totals['weekly_seconds'],600)

    async def test_goals_links_progress_edit_archive_delete_and_zero_ai(self):
        p,cols=await self.project();task=await self.task(p,cols[3]);base=f'/projects/{p["id"]}/focus/goals'
        data={'title':'Ship project','description':'Deliver value','target_date':'2026-12-01','milestones':[{'title':'Design','completed':False}],'task_ids':[task['id']]}
        row=await self.ok('POST',base,201,json=data);self.assertEqual(row['progress'],50)
        row=await self.ok('PUT',base+f'/{row["id"]}',json={**data,'revision':1,'milestones':[{'title':'Design','completed':True}],'status':'archived'})
        self.assertEqual(row['progress'],100);self.assertEqual(row['status'],'archived')
        await self.ok('PUT',base+f'/{row["id"]}',409,json={**data,'revision':1})
        await self.ok('DELETE',base+f'/{row["id"]}',json={'revision':2});self.assertEqual(f.FakeClient.calls,[])

    async def test_owner_project_isolation_archived_writes_and_delete_retention(self):
        p,cols=await self.project();task=await self.task(p,cols[0]);other,ocols=await self.project('Other');otask=await self.task(other,ocols[0])
        await self.ok('POST','/focus/sessions',404,json={'project_id':p['id'],'task_id':otask['id']})
        await self.ok('POST',f'/projects/{p["id"]}/focus/goals',404,json={'title':'Wrong task','task_ids':[otask['id']]})
        g=await self.ok('POST',f'/projects/{p["id"]}/focus/goals',201,json={'title':'Private'})
        row=await self.start(project_id=p['id'],task_id=task['id']);saved=self.headers
        u=await self.client.post('/auth/signup',json={'email':f'{__import__("uuid").uuid4().hex}@example.com','password':'password123'});self.headers={'Authorization':'Bearer '+u.json()['token']}
        await self.ok('GET',f'/focus/sessions/{row["id"]}',404);await self.act(row,'pause',404)
        await self.ok('GET',f'/projects/{p["id"]}/focus/goals/{g["id"]}',404)
        await self.ok('GET',f'/time/entries?project_id={p["id"]}',404)
        self.assertIsNone((await self.ok('GET','/focus/active'))['session'])
        self.assertEqual((await self.ok('GET','/time/entries'))['items'],[])
        self.headers=saved;await self.act(row,'stop')
        entries=(await self.ok('GET','/time/entries'))['items'];self.assertEqual(len(entries),1)
        await self.ok('PATCH',f'/projects/{p["id"]}',json={'revision':1,'archived':True})
        await self.ok('POST','/focus/sessions',409,json={'project_id':p['id']})
        await self.ok('DELETE',f'/projects/{p["id"]}',json={'revision':2,'confirm_name':p['name']})
        retained=await self.ok('GET',f'/focus/sessions/{row["id"]}');self.assertIsNone(retained['project_id']);self.assertIsNone(retained['task_id'])
        with SessionLocal() as db:self.assertEqual(db.execute(text('PRAGMA foreign_key_check')).all(),[])

if __name__=='__main__':unittest.main()
