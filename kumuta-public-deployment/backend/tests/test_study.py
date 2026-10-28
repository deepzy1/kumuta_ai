"""Learning contracts against disposable SQLite and the existing fake provider."""
import json
import unittest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text
import test_api as f
import test_workspaces as w
from app import documents
from app.database import SessionLocal, Usage
from app.study_models import Card, Course

class StudyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = f.APITests.asyncSetUp
    asyncTearDown = f.APITests.asyncTearDown
    call = f.APITests.call
    connect = f.APITests.connect
    ok = w.WorkspaceAPITests.ok
    project = w.WorkspaceAPITests.project
    task = w.WorkspaceAPITests.task

    async def setup_course(self):
        p, cols = await self.project(); self.pid = p['id']; self.base = f'/projects/{self.pid}/study'
        c = await self.ok('POST', self.base+'/courses', 201, json={'title':'Python','objectives':'Understand SQLite'})
        return p, cols, c

    async def create(self, kind, **data): return await self.ok('POST',self.base+'/'+kind,201,json=data)
    async def edit(self, kind, row, **changes):
        from app.study_api import REGISTRY
        schema = REGISTRY[kind][1]
        data = {k: row[k] for k in schema.model_fields}; data.update(changes, revision=row['revision'])
        return await self.ok('PUT',f'{self.base}/{kind}/{row["id"]}',json=data)

    async def test_courses_lessons_resources_reorder_archive_and_no_ai(self):
        p,cols,c = await self.setup_course()
        ch = await self.create('chapters',course_id=c['id'],title='Basics')
        ch2 = await self.create('chapters',course_id=c['id'],title='Advanced')
        a = await self.create('lessons',course_id=c['id'],chapter_id=ch['id'],title='A',content='# SQLite',notes='Personal')
        b = await self.create('lessons',course_id=c['id'],chapter_id=ch['id'],title='B')
        await self.edit('lessons',a,completed=True)
        course = await self.ok('GET',f'{self.base}/courses/{c["id"]}')
        self.assertEqual(course['progress'],50);self.assertEqual(course['continue_lesson_id'],b['id'])
        await self.ok('POST',f'{self.base}/lessons/{b["id"]}/move',json={'revision':1,'before_id':a['id']})
        self.assertEqual((await self.ok('GET',self.base+'/lessons'))['items'][0]['id'],b['id'])
        await self.ok('POST',f'{self.base}/chapters/{ch2["id"]}/move',json={'revision':1,'before_id':ch['id']})
        await self.ok('PUT',f'{self.base}/lessons/{a["id"]}',409,json={**{k:a[k] for k in ('course_id','chapter_id','title')},'revision':1})
        await self.create('resources',course_id=c['id'],title='Python',url='https://python.org')
        await self.ok('POST',self.base+'/resources',422,json={'course_id':c['id'],'title':'Unsafe','url':'javascript:alert(1)'})
        await self.edit('courses',c,archived=True)
        self.assertEqual(len((await self.ok('GET',self.base+'/courses?archived=true&q=Python'))['items']),1)
        self.assertEqual(f.FakeClient.calls,[])

    async def test_quiz_four_types_scoring_snapshot_retry_and_validation(self):
        _,_,c=await self.setup_course()
        qs=[{'prompt':'Pick A','kind':'single','options':['A','B'],'answers':['A'],'explanation':'A is correct'},
            {'prompt':'Pick A and C','kind':'multiple','options':['A','B','C'],'answers':['A','C']},
            {'prompt':'SQLite is local','kind':'boolean','options':['True','False'],'answers':['True']},
            {'prompt':'Database','kind':'short','answers':['SQLite','sqlite3']}]
        q=await self.create('quizzes',course_id=c['id'],title='Quiz',questions=qs)
        path=f'{self.base}/quizzes/{q["id"]}/attempts'
        await self.ok('POST',path,409,json={'revision':1,'answers':[['A'],['A','C'],['True'],['SQLite']]})
        q=await self.edit('quizzes',q,published=True)
        r=await self.ok('POST',path,201,json={'revision':2,'answers':[['A'],['A'],['True'],['  SQLITE  ']]})
        self.assertEqual((r['score'],r['total']),(3,4));self.assertFalse(r['result'][1]['correct'])
        await self.ok('POST',path,422,json={'revision':2,'answers':[['forged'],[],[],[]]})
        await self.ok('POST',path,422,json={'revision':2,'answers':[]})
        await self.ok('POST',path,201,json={'revision':2,'answers':[['A'],['C','A'],['True'],['sqlite3']]})
        q=await self.edit('quizzes',q,title='Edited quiz')
        history=(await self.ok('GET',self.base+f'/attempts?identity={q["id"]}'))['items']
        self.assertEqual(len(history),2);self.assertEqual(history[0]['score'],4)
        self.assertEqual(history[1]['result'][0]['explanation'],'A is correct')
        self.assertEqual(f.FakeClient.calls,[])

    async def test_fsrs_persists_all_ratings_stale_and_due_checks(self):
        _,_,c=await self.setup_course();d=await self.create('decks',course_id=c['id'],title='Deck')
        for rating in range(1,5):
            card=await self.create('cards',deck_id=d['id'],front=f'Front {rating}',back='Back')
            path=f'{self.base}/cards/{card["id"]}/review'
            reviewed=await self.ok('POST',path,201,json={'revision':1,'rating':rating})
            self.assertEqual(reviewed['reviews'],1);self.assertGreater(reviewed['due_at'],card['due_at'])
            await self.ok('POST',path,409,json={'revision':1,'rating':rating})
            await self.ok('POST',path,409,json={'revision':2,'rating':rating})
            await self.edit('cards',reviewed,back='New back')
            with SessionLocal() as db:
                stored=db.get(Card,card['id']);self.assertEqual(json.loads(stored.schedule)['due'],reviewed['due_at'])
                stored.due_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();db.commit()
            await self.ok('POST',path,201,json={'revision':3,'rating':3})
            self.assertEqual(len((await self.ok('GET',self.base+f'/reviews?identity={card["id"]}'))['items']),2)
        self.assertEqual(f.FakeClient.calls,[])

    async def test_plan_links_progress_reschedule_and_project_cascade(self):
        p,cols,c=await self.setup_course();task=await self.task(p,cols[3])
        plan=await self.create('plans',title='Learn Python',course_ids=[c['id']],task_ids=[task['id']],
            milestones=[{'title':'Milestone','completed':True}],sessions=[{'title':'Read','starts_at':'2026-10-12T18:00:00+05:30','minutes':30,'completed':True}])
        self.assertEqual(plan['progress'],75)
        plan=await self.edit('plans',plan,target_date='2026-12-01',cadence='weekly',target_minutes=120)
        self.assertEqual(plan['task_ids'],[task['id']])
        await self.ok('DELETE',f'/projects/{p["id"]}',json={'revision':p['revision'],'confirm_name':p['name']})
        with SessionLocal() as db:
            self.assertIsNone(db.get(Course,c['id']));self.assertEqual(db.execute(text('PRAGMA foreign_key_check')).all(),[])
        self.assertEqual(f.FakeClient.calls,[])

    async def test_authorization_all_resources_and_cross_project_references(self):
        p,cols,c=await self.setup_course();ch=await self.create('chapters',course_id=c['id'],title='Ch')
        lesson=await self.create('lessons',course_id=c['id'],chapter_id=ch['id'],title='L')
        q=await self.create('quizzes',course_id=c['id'],title='Q',questions=[{'prompt':'Q','kind':'short','answers':['A']}])
        deck=await self.create('decks',course_id=c['id'],title='D');card=await self.create('cards',deck_id=deck['id'],front='F',back='B')
        plan=await self.create('plans',title='Plan')
        other,_=await self.project('Other'); op=other['id']
        for kind,row in [('courses',c),('chapters',ch),('lessons',lesson),('quizzes',q),('decks',deck),('cards',card),('plans',plan)]:
            await self.ok('GET',f'/projects/{op}/study/{kind}/{row["id"]}',404)
        await self.ok('POST',f'/projects/{op}/study/chapters',404,json={'course_id':c['id'],'title':'Forged'})
        saved=self.headers
        user=await self.client.post('/auth/signup',json={'email':f'{__import__("uuid").uuid4().hex}@example.com','password':'password123'})
        self.headers={'Authorization':'Bearer '+user.json()['token']}
        for kind,row in [('courses',c),('chapters',ch),('lessons',lesson),('quizzes',q),('decks',deck),('cards',card),('plans',plan)]:
            await self.ok('GET',self.base+f'/{kind}/{row["id"]}',404)
            await self.ok('DELETE',self.base+f'/{kind}/{row["id"]}',404,json={'revision':1})
        await self.ok('GET',self.base+f'/reviews?identity={card["id"]}',404)
        await self.ok('GET',self.base+f'/attempts?identity={q["id"]}',404)
        self.headers=saved

    async def test_tutor_existing_stream_documents_memory_history_and_usage(self):
        p,_,c=await self.setup_course()
        doc=await self.ok('POST','/documents',201,files={'file':('reference.txt',b'SQLite supports local learning records.')},data={'project_id':self.pid})
        while documents.process_next(): pass
        await self.create('resources',course_id=c['id'],title='Reference',document_id=doc['id'])
        cid=(await self.ok('POST','/conversations',json={'project_id':self.pid}))['id']
        await self.ok('POST','/memories',201,json={'scope':'project','project_id':self.pid,'content':'I study SQLite at beginner level.','consent':True})
        await self.ok('PUT','/settings/memory',json={'scope':'global','enabled':True,'revision':0})
        await self.connect();f.FakeClient.calls.clear()
        controls=json.dumps({'course_id':c['id'],'level':'advanced','depth':'detailed'})
        response=await self.call('POST',f'/conversations/{cid}/messages',data={'text':'Explain SQLite','tutor_request':controls})
        self.assertEqual(response.status_code,200,response.text)
        streamed=next(x for x in f.FakeClient.calls if x[0]=='stream')[2]
        self.assertIn('Learning level: advanced',streamed['config'].system_instruction)
        payload=str(streamed['contents']);self.assertIn('UNTRUSTED DOCUMENT EVIDENCE',payload);self.assertIn('I study SQLite',payload)
        await self.call('POST',f'/conversations/{cid}/regenerate')
        stored=await self.ok('GET',f'/conversations/{cid}')
        self.assertEqual(next(x for x in stored['messages'] if x['role']=='user')['document_request']['tutor']['depth'],'detailed')
        with SessionLocal() as db:self.assertTrue(list(db.scalars(select(Usage).where(Usage.conversation_id==cid))))
        other,_=await self.project('Other')
        othercid=(await self.ok('POST','/conversations',json={'project_id':other['id']}))['id']
        await self.ok('POST',f'/conversations/{othercid}/messages',404,data={'text':'Explain','tutor_request':controls})

if __name__=='__main__':unittest.main()
