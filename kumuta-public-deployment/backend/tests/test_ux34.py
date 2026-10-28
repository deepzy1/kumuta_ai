"""Guided learning and review-first analysis use real owned resources, fake providers."""
import json
import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select
from app import gemini, study_generation
from app.database import SessionLocal, Usage, Message, Attachment
from app.document_models import Document, DocumentChunk
from app.study_models import Course
from fastapi import HTTPException
import test_api as fixture
import test_ux as ux_fixture

OUTLINE = {'title':'Learn Python','description':'A short course','objectives':'Use variables', 'origin':'ai',
           'chapters':[{'title':'Basics','lessons':[{'title':'Variables','content':'A variable stores a value.\n\n## Practice\nCreate a variable.'},
                                                   {'title':'Types','content':'Compare a number and text.'}]}]}

class GuidedTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=ux_fixture.UXTests.asyncSetUp
    asyncTearDown=ux_fixture.UXTests.asyncTearDown
    call=ux_fixture.UXTests.call
    ok=ux_fixture.UXTests.ok
    project=ux_fixture.UXTests.project
    upload=ux_fixture.UXTests.upload

    async def test_course_draft_review_atomic_save_and_progress(self):
        project, _ = await self.project('Guided study')
        await fixture.APITests.connect(self)
        async def generate(client, **kwargs):
            self.assertEqual(kwargs['model'], 'gemini-test-flash')
            self.assertEqual(json.loads(kwargs['contents'][0].parts[0].text)['objective'], 'Use variables')
            return SimpleNamespace(text=json.dumps(OUTLINE),usage_metadata=None)
        path=f'/projects/{project["id"]}/study'
        with patch.object(fixture.FakeClient,'generate_content',generate):
            draft=await self.ok('POST',path+'/draft',json={'topic':'Python','objective':'Use variables'})
        self.assertEqual((await self.ok('GET',path+'/courses'))['items'],[],'Draft must not persist')
        draft['outline']['title']='Reviewed course'
        saved=await self.ok('POST',path+'/outline',status=201,json={'outline':draft['outline']})
        self.assertEqual(saved['title'],'Reviewed course');self.assertEqual(saved['lesson_count'],2)
        await self.ok('POST',path+'/outline',status=422,json={'outline':OUTLINE|{'description':'学'*17000}})
        self.assertEqual(len((await self.ok('GET',path+'/courses'))['items']),1)
        lessons=(await self.ok('GET',path+'/lessons'))['items']
        lesson=lessons[0]
        await self.ok('PUT',f'{path}/lessons/{lesson["id"]}',json={k:lesson[k] for k in ('title','course_id','chapter_id','content','notes','origin','revision')}|{'completed':True})
        self.assertEqual((await self.ok('GET',f'{path}/courses/{saved["id"]}'))['progress'],50)
        with SessionLocal() as db:
            usage=db.scalar(select(Usage).where(Usage.kind=='study_course').order_by(Usage.id.desc()))
            self.assertEqual(usage.status,'complete')

    async def test_source_confirmation_authorization_and_invalid_output(self):
        project,_=await self.project('Sources');other,_=await self.project('Foreign')
        doc=await self.upload(project_id=project['id']);foreign=await self.upload(project_id=other['id'])
        path=f'/projects/{project["id"]}/study'
        await self.ok('POST',path+'/draft',status=422,json={'topic':'Source','source':'document','document_id':doc['id']})
        await self.ok('POST',path+'/draft',status=404,json={'topic':'Source','source':'document','document_id':foreign['id'],'confirm_source':True})
        await self.ok('POST',path+'/outline',status=404,json={'outline':OUTLINE,'document_id':foreign['id']})
        self.assertEqual((await self.ok('GET',path+'/courses'))['items'],[])
        self.assertEqual(fixture.FakeClient.calls,[])
        await fixture.APITests.connect(self)
        await self.ok('POST',path+'/draft',status=422,json={'topic':'Invalid response'})
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(Usage).where(Usage.kind=='study_course').order_by(Usage.id.desc())).status,'invalid_outline')
        with SessionLocal() as db:
            row=db.get(Document,doc['id']);row.status='ready';chunk=db.scalar(select(DocumentChunk).where(DocumentChunk.document_id==row.id).order_by(DocumentChunk.ordinal));chunk.content='Owned source text';db.commit()
        async def generate(client,**kwargs):
            source=json.loads(kwargs['contents'][0].parts[0].text)['source']
            self.assertIn('Owned source text',source['excerpt'])
            return SimpleNamespace(text=json.dumps(OUTLINE),usage_metadata=None)
        with patch.object(fixture.FakeClient,'generate_content',generate):
            result=await self.ok('POST',path+'/draft',json={'topic':'Source','source':'document','document_id':doc['id'],'confirm_source':True})
        self.assertNotIn('excerpt',result['source'])
        saved=await self.ok('POST',path+'/outline',status=201,json={'outline':result['outline'],'document_id':doc['id']})
        resources=(await self.ok('GET',path+'/resources'))['items']
        self.assertEqual(resources[0]['document_id'],doc['id']);self.assertEqual(resources[0]['course_id'],saved['id'])

    def test_url_fetch_boundary(self):
        for url in ['http://en.wikipedia.org/wiki/Python','https://127.0.0.1/wiki/Python','https://en.wikipedia.org.evil.test/wiki/Python',
                    'https://x@en.wikipedia.org/wiki/Python','https://en.wikipedia.org:444/wiki/Python','https://en.wikipedia.org/wiki/Special:Test','https://en.wikipedia.org/wiki/Python?x=1']:
            with self.assertRaises(HTTPException):study_generation.wikipedia_title(url)
        self.assertEqual(study_generation.wikipedia_title('https://en.wikipedia.org/wiki/Python_(programming_language)'),'Python_(programming_language)')
        with self.assertRaises(HTTPException):study_generation.NoRedirect().redirect_request(None,None,None,None,None,None)
        url='https://en.wikipedia.org/wiki/Python_(programming_language)'
        with patch.object(study_generation,'build_opener') as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value=json.dumps({'query':{'pages':{'1':{'extract':'Verified test article excerpt'}}}}).encode()
            source=study_generation.url_source(url)
            self.assertEqual(source['excerpt'],'Verified test article excerpt');self.assertEqual(source['url'],url)
            self.assertTrue(opener.return_value.open.call_args.args[0].full_url.startswith('https://en.wikipedia.org/w/api.php?'))
            response.read.assert_called_once_with(512001)
            response.read.return_value=b'x'*512001
            with self.assertRaises(HTTPException):study_generation.url_source(url)

    async def test_chat_pdf_import_deduplicates_and_checks_conversation_membership(self):
        project,_=await self.project('Imports')
        chat=await self.ok('POST','/conversations',json={'project_id':project['id']})
        source=b'%PDF-1.7\nretained original source'
        with SessionLocal() as db:
            message=Message(conversation_id=chat['id'],role='user',content='Read this')
            db.add(message);db.flush()
            attachment=Attachment(message_id=message.id,attachment_name='source.pdf',attachment_mime='application/pdf',attachment_size=len(source),attachment_data=base64.b64encode(source).decode())
            db.add(attachment);db.commit();mid,aid=message.id,attachment.id
        path=f'/conversations/{chat["id"]}/attachments/{mid}/library'
        doc=await self.ok('POST',path,status=201,json={'attachment_id':aid})
        repeated=await self.ok('POST',path,status=201,json={'attachment_id':aid})
        self.assertEqual(doc['id'],repeated['id']);self.assertTrue(repeated['duplicate'])
        self.assertEqual((await self.call('GET',f'/documents/{doc["id"]}/file')).content,source)
        other=await self.ok('POST','/conversations',json={'project_id':project['id']})
        await self.ok('POST',f'/conversations/{other["id"]}/attachments/{mid}/library',status=404,json={'attachment_id':aid})
        second=await self.client.post('/auth/signup',json={'email':__import__('uuid').uuid4().hex+'@test.com','password':'password123'})
        result=await self.client.post(path,headers={'Authorization':'Bearer '+second.json()['token']},json={'attachment_id':aid})
        self.assertEqual(result.status_code,404)
        self.assertEqual(fixture.FakeClient.calls,[])

    async def test_interpretation_returns_validated_spec_only_before_local_result(self):
        from test_datasets import DatasetTests
        from test_data_analysis import SOURCE
        project,_=await self.project('Reviewed analysis')
        other,_=await self.project('Other project')
        dataset=await DatasetTests.upload(self,project['id'],data=SOURCE)
        await fixture.APITests.connect(self)
        async def generate(client,**kwargs):
            payload=json.loads(kwargs['contents'][0].parts[0].text)
            self.assertEqual(set(payload),{'question','sheet','columns'})
            self.assertNotIn('10.5',str(payload));self.assertNotIn('ignore instructions',str(payload))
            return SimpleNamespace(text=json.dumps({'metrics':[{'op':'sum','column':'revenue','alias':'Revenue'}]}),usage_metadata=None)
        base=f'/projects/{project["id"]}/data'
        with patch.object(fixture.FakeClient,'generate_content',generate):
            review=await self.ok('POST',base+'/interpret',json={'dataset_id':dataset['id'],'question':'Total revenue'})
        self.assertIn('spec',review);self.assertNotIn('rows',review)
        local=await self.ok('POST',base+f'/datasets/{dataset["id"]}/analyze',json=review['spec'])
        self.assertEqual(local['rows'],[['35.5']]);self.assertEqual(local['ai_calls'],0)
        await self.ok('POST',f'/projects/{other["id"]}/data/interpret',status=404,json={'dataset_id':dataset['id'],'question':'Total'})
        async def invalid(client,**kwargs):
            return SimpleNamespace(text=json.dumps({'metrics':[{'op':'sum','column':'unavailable','alias':'Total'}]}),usage_metadata=None)
        with patch.object(fixture.FakeClient,'generate_content',invalid):
            await self.ok('POST',base+'/interpret',status=422,json={'dataset_id':dataset['id'],'question':'Total'})

    async def test_moved_source_is_hidden_from_course_and_new_routes_reject_other_users(self):
        from app.database import Conversation
        from app.study_models import Resource
        project,_=await self.project('Original');other,_=await self.project('Moved')
        chat=await self.ok('POST','/conversations',json={'project_id':project['id']})
        doc=await self.upload(conversation_id=chat['id'])
        path=f'/projects/{project["id"]}/study'
        saved=await self.ok('POST',path+'/outline',status=201,json={'outline':OUTLINE,'document_id':doc['id']})
        with SessionLocal() as db:
            conversation=db.get(Conversation,chat['id']);conversation.project_id=other['id'];db.commit()
        resource=(await self.ok('GET',path+'/resources'))['items'][0]
        self.assertIsNone(resource['document_id']);self.assertFalse(resource['source_available'])
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(Resource.document_id).where(Resource.course_id==saved['id'])),doc['id'],'Preserve original source association')
        second=await self.client.post('/auth/signup',json={'email':__import__('uuid').uuid4().hex+'@test.com','password':'password123'})
        headers={'Authorization':'Bearer '+second.json()['token']}
        for endpoint,payload in [('/draft',{'topic':'Tampering'}),('/outline',{'outline':OUTLINE})]:
            response=await self.client.post(path+endpoint,headers=headers,json=payload)
            self.assertEqual(response.status_code,404)
        self.assertEqual(fixture.FakeClient.calls,[])
