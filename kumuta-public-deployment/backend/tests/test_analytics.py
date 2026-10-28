"""Reporting accuracy, security, DST, time ledger, history and zero AI."""
import csv
import io
import json
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select
import test_api as fixture
import test_workspaces as workspace
import test_study as study
from app import analytics, focus
from app.database import SessionLocal
from app import study_models as s
from app.workspace_models import Task


class AnalyticsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.APITests.asyncSetUp
    asyncTearDown = fixture.APITests.asyncTearDown
    call = fixture.APITests.call
    ok = workspace.WorkspaceAPITests.ok
    project = workspace.WorkspaceAPITests.project
    task = workspace.WorkspaceAPITests.task
    board_revision = workspace.WorkspaceAPITests.board_revision
    setup_course = study.StudyTests.setup_course
    create = study.StudyTests.create
    edit = study.StudyTests.edit

    async def report(self, **filters):
        result = await self.ok('GET', '/analytics', params=filters)
        self.assertEqual(fixture.FakeClient.calls, [])
        return result

    async def test_empty_unavailable_zero_and_csv(self):
        r = await self.report(preset='today', tz='Asia/Calcutta')
        self.assertEqual(r['range']['timezone'], 'Asia/Kolkata')
        self.assertEqual(r['study']['quiz_attempts'], 0)
        self.assertIsNone(r['study']['average_quiz_score'])
        self.assertIsNone(r['study']['completion_percentage'])
        self.assertEqual(r['focus']['total_seconds'], 0)
        self.assertIsNone(r['focus']['average_session_seconds'])
        self.assertEqual(len(r['daily']), 1)
        self.assertEqual(r['ai_calls'], 0)
        response = await self.call('GET', '/analytics/export?kind=study&preset=today')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertIn('attachment;', response.headers['content-disposition'])
        rows = list(csv.reader(io.StringIO(response.text)))
        self.assertIn(['study.study_seconds', '', 'See metric definitions in report limitations'], rows)

    async def test_study_accuracy_progress_quizzes_cards_and_date_filters(self):
        p, cols, course = await self.setup_course()
        chapter = await self.create('chapters', course_id=course['id'], title='Chapter')
        a = await self.create('lessons', course_id=course['id'], chapter_id=chapter['id'], title='A', completed=True)
        await self.create('lessons', course_id=course['id'], chapter_id=chapter['id'], title='B')
        quiz = await self.create('quizzes', course_id=course['id'], title='Q', questions=[{'kind':'boolean','prompt':'Yes?','options':['True','False'],'answers':['True']}], published=True)
        for answer in ('True', 'False'):
            await self.ok('POST', f'{self.base}/quizzes/{quiz["id"]}/attempts', 201, json={'revision':1,'answers':[[answer]]})
        deck = await self.create('decks', course_id=course['id'], title='Deck')
        card = await self.create('cards', deck_id=deck['id'], front='Q', back='A')
        await self.ok('POST', f'{self.base}/cards/{card["id"]}/review', 201, json={'revision':1,'rating':3})
        plan = await self.create('plans', title='Plan', course_ids=[course['id']], milestones=[{'title':'M','completed':True}],
                                 sessions=[{'title':'S','starts_at':'2026-10-10T12:00:00+00:00','minutes':30,'completed':True}])
        with SessionLocal() as db:
            db.get(s.Lesson, a['id']).completed_at = '2026-10-10T20:00:00+00:00'
            for model in (s.Attempt, s.Review):
                for row in db.scalars(select(model).where(model.project_id == p['id'])):
                    row.created_at = '2026-10-10T20:00:00+00:00'
            db.commit()
        r = await self.report(project_id=p['id'], course_id=course['id'], preset='custom', start='2026-10-11', end='2026-10-11', tz='Asia/Kolkata')
        self.assertEqual(r['study']['completion_percentage'], 50)
        self.assertEqual(r['study']['quiz_attempts'], 2)
        self.assertEqual(r['study']['average_quiz_score'], 50)
        self.assertEqual(r['study']['flashcards_reviewed'], 1)
        self.assertEqual(r['study']['review_success_percentage'], 100)
        self.assertEqual(r['daily'][0]['lessons'], 1)
        self.assertEqual(r['study']['streak_at_range_end'], 1)
        self.assertEqual(r['study']['plans']['items'][0]['progress'], plan['progress'])
        self.assertEqual(r['study']['completed_planned_minutes_on_page'], 0)
        old = await self.report(project_id=p['id'], preset='custom', start='2026-10-10', end='2026-10-10', tz='UTC')
        self.assertEqual(old['study']['completed_planned_minutes_on_page'], 30)
        self.assertEqual(r['study']['quiz_performance']['items'][0]['attempts'], 2)

    async def test_segments_pauses_adjustments_and_no_double_count(self):
        p, _ = await self.project()
        t = datetime(2026,10,10,18,20,tzinfo=timezone.utc)
        with patch.object(focus, 'clock', return_value=t):
            row = await self.ok('POST','/focus/sessions',201,json={'project_id':p['id'],'planned_seconds':3600})
        with patch.object(focus, 'clock', return_value=t+timedelta(minutes=20)):
            paused = await self.ok('POST',f'/focus/sessions/{row["id"]}/pause',json={'revision':row['revision']})
        with patch.object(focus, 'clock', return_value=t+timedelta(hours=2)):
            resumed = await self.ok('POST',f'/focus/sessions/{row["id"]}/resume',json={'revision':paused['revision']})
        with patch.object(focus, 'clock', return_value=t+timedelta(hours=2,minutes=10)):
            await self.ok('POST',f'/focus/sessions/{row["id"]}/stop',json={'revision':resumed['revision']})
        filters = dict(project_id=p['id'],preset='custom',start='2026-10-10',end='2026-10-11',tz='Asia/Kolkata')
        r = await self.report(**filters)
        self.assertEqual(r['focus']['total_seconds'],1800)
        self.assertEqual([x['focus_seconds'] for x in r['daily']],[600,1200])
        self.assertEqual(r['focus']['session_count'],1)
        self.assertEqual(r['focus']['average_session_seconds'],1800)
        self.assertEqual(sum(x['focus_seconds'] for x in r['weekly']),1800)
        self.assertEqual(sum(x['focus_seconds'] for x in r['monthly']),1800)
        entry = (await self.ok('GET',f'/time/entries?project_id={p["id"]}'))['items'][0]
        await self.ok('PUT',f'/time/entries/{entry["id"]}',json={'revision':entry['revision'],'project_id':p['id'],
            'started_at':t.isoformat(),'ended_at':(t+timedelta(minutes=10)).isoformat()})
        adjusted = await self.report(**filters)
        self.assertEqual(adjusted['focus']['total_seconds'],600)
        self.assertEqual(adjusted['focus']['average_session_seconds'],1800)
        await self.ok('DELETE',f'/time/entries/{entry["id"]}',json={'revision':2})
        self.assertEqual((await self.report(**filters))['focus']['total_seconds'],0)

    async def test_natural_completion_idempotence_active_and_breaks(self):
        p, _ = await self.project()
        t = datetime(2026,10,10,10,tzinfo=timezone.utc)
        with patch.object(focus,'clock',return_value=t):
            await self.ok('POST','/focus/sessions',201,json={'project_id':p['id'],'planned_seconds':60})
            active = await self.report(project_id=p['id'],preset='today')
            self.assertEqual(active['focus']['total_seconds'],0)
            self.assertIsNotNone(active['focus']['active_session'])
        with patch.object(focus,'clock',return_value=t+timedelta(minutes=5)):
            for _ in range(2):
                r = await self.report(project_id=p['id'],preset='today')
                self.assertEqual(r['focus']['total_seconds'],60)
                self.assertEqual(r['focus']['session_count'],1)
            await self.ok('POST','/focus/sessions',201,json={'project_id':p['id'],'kind':'short_break','planned_seconds':60})
        with patch.object(focus,'clock',return_value=t+timedelta(minutes=10)):
            r = await self.report(project_id=p['id'],preset='today')
            self.assertEqual(r['focus']['total_seconds'],60)
            self.assertEqual(r['focus']['session_count'],1)

    async def test_scope_authorization_and_exports(self):
        p, cols, c = await self.setup_course()
        other, other_cols = await self.project(name='Other')
        await self.task(other, other_cols[-1])
        await self.ok('GET','/analytics',404,params={'project_id':other['id'],'course_id':c['id']})
        self.assertEqual((await self.report(project_id=p['id']))['workspace']['tasks'],0)
        before = self.headers
        second = await self.client.post('/auth/signup',json={'email':f'other-{time.time_ns()}@test.com','password':'password123'})
        self.headers={'Authorization':'Bearer '+second.json()['token']}
        for path in ('/analytics','/analytics/export'):
            for values in ({'project_id':p['id']},{'workspace_id':p['workspace_id']},{'course_id':c['id']}):
                await self.ok('GET',path,404,params=values)
        self.assertEqual((await self.report())['study']['lessons'],0)
        self.headers=before

    async def test_invalid_inputs_and_pagination(self):
        for values in ({'tz':'Mars/Unknown'},{'preset':'custom'},{'preset':'custom','start':'2026-10-12','end':'2026-10-11'},
                       {'preset':'custom','start':'2025-01-01','end':'2026-10-12'},{'start':'2026-10-01'},
                       {'limit':201},{'offset':-1},{'preset':'invalid'},
                       {'preset':'custom','start':'9999-12-31','end':'9999-12-31'},
                       {'preset':'custom','start':'0001-01-01','end':'0001-01-01','tz':'Asia/Kolkata'}):
            await self.ok('GET','/analytics',422,params=values)
        p, cols, c = await self.setup_course()
        await self.create('courses',title='Second')
        r=await self.report(project_id=p['id'],limit=1)
        self.assertTrue(r['study']['courses']['has_more'])
        page=await self.report(project_id=p['id'],limit=1,offset=1)
        self.assertEqual(page['study']['courses']['items'][0]['title'],'Second')
        self.assertEqual(len(r['daily']),30)

    async def test_completion_dates_and_reopen_column_transition(self):
        p, cols, c = await self.setup_course()
        row=await self.task(p,cols[-1])
        self.assertIsNotNone(row['completed_at'])
        stamp=row['completed_at']
        row=(await self.ok('PATCH',f'/projects/{p["id"]}/tasks/{row["id"]}',json={'revision':row['revision'],'title':'Edited'}))['task']
        self.assertEqual(row['completed_at'],stamp)
        row=(await self.ok('POST',f'/projects/{p["id"]}/tasks/{row["id"]}/move',json={'column_id':cols[0]['id'],'board_revision':await self.board_revision(p['id'])}))['task']
        self.assertIsNone(row['completed_at'])
        await self.ok('PATCH',f'/projects/{p["id"]}/columns/{cols[0]["id"]}',json={'board_revision':await self.board_revision(p['id']),'is_done':True})
        row=await self.ok('GET',f'/projects/{p["id"]}/tasks/{row["id"]}')
        self.assertIsNotNone(row['completed_at'])
        self.assertEqual((await self.report(project_id=p['id'],preset='today'))['workspace']['tasks_completed_in_range'],1)
        with SessionLocal() as db:
            db.get(Task,row['id']).completed_at=None;db.commit()
        r=await self.report(project_id=p['id'],preset='today')
        self.assertEqual(r['workspace']['unknown_completion_dates'],1)
        self.assertEqual(r['workspace']['tasks_completed_in_range'],0)

    def test_dst_allocation_and_csv_formula_safety(self):
        _,days,bounds=analytics.window('custom',date(2026,3,8),date(2026,3,8),'America/New_York',datetime.now(timezone.utc))
        self.assertEqual((bounds[-1]-bounds[0]).total_seconds(),23*3600)
        row=SimpleNamespace(segments=json.dumps([[bounds[0].isoformat(),bounds[-1].isoformat()]]),allocation_estimated=False,duration_seconds=23*3600)
        self.assertEqual(analytics.allocate(row,bounds)[0],[23*3600])
        _,_,bounds=analytics.window('custom',date(2026,11,1),date(2026,11,1),'America/New_York',datetime.now(timezone.utc))
        self.assertEqual((bounds[-1]-bounds[0]).total_seconds(),25*3600)
        row=SimpleNamespace(segments='[]',allocation_estimated=True,duration_seconds=3600,started_at=bounds[0].isoformat(),ended_at=bounds[-1].isoformat())
        self.assertEqual(analytics.allocate(row,bounds),([3600],True))
        data={'range':{'start':'=EVIL','end':'end','timezone':'UTC'},'study':{'x':None},'daily':[],'limitations':['  =SUM(1,2)','@cmd','+cmd','-cmd','\tformula']}
        rows=list(csv.reader(io.StringIO(analytics.export_csv(data,'study'))))
        self.assertEqual(rows[0][2],"'=EVIL")
        for row in rows[4:]: self.assertTrue(row[1].startswith("'"))

    async def test_large_dataset_aggregates_are_not_limited_by_detail_pages(self):
        from sqlalchemy import insert, event
        from app.database import engine
        p, _, c = await self.setup_course()
        q = await self.create('quizzes',course_id=c['id'],title='Large',questions=[{'kind':'boolean','prompt':'Q','options':['True','False'],'answers':['True']}])
        with SessionLocal() as db:
            db.execute(insert(s.Attempt),[{'owner_id':db.get(s.Course,c['id']).owner_id,'project_id':p['id'],
                'quiz_id':q['id'],'quiz_revision':1,'result':'[]','score':i%2,'total':1,'created_at':'2026-10-10T12:00:00+00:00'} for i in range(20000)])
            db.commit()
        queries=[]
        def count(conn,cursor,statement,*args):queries.append(statement)
        event.listen(engine,'before_cursor_execute',count)
        started=time.perf_counter()
        try:r=await self.report(project_id=p['id'],preset='custom',start='2026-10-10',end='2026-10-10',limit=1)
        finally:event.remove(engine,'before_cursor_execute',count)
        elapsed=time.perf_counter()-started
        self.assertEqual(r['study']['quiz_attempts'],20000)
        self.assertEqual(r['daily'][0]['quiz_attempts'],20000)
        self.assertEqual(r['study']['average_quiz_score'],50)
        self.assertLess(len(queries),55)
        print(f'Analytics benchmark: 20000 attempts, {len(queries)} SQL statements, {elapsed:.3f}s')
