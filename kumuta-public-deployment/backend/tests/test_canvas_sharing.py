"""D7-8 adversarial sharing/session contracts; disposable SQLite, no live Gemini."""
import asyncio
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from sqlalchemy import select, update
from starlette.requests import Request
import test_boards as fixture
from app import boards, browser_sessions as browser, canvas_generation as generation, database, gemini, main
from app.board_models import BoardMember, BoardSceneRevision
from app.canvas_generation_models import GenerationJob as Job, GenerationEvent as Event
from app.database import User, Usage


class SharingTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixture.BoardAPITests.asyncSetUp
    asyncTearDown=fixture.BoardAPITests.asyncTearDown
    ok=fixture.BoardAPITests.ok
    board=fixture.BoardAPITests.board
    save=fixture.BoardAPITests.save
    project=fixture.BoardAPITests.project
    document=fixture.BoardAPITests.document
    conversation=fixture.BoardAPITests.conversation

    async def account(self,email):
        result=(await self.client.post('/auth/signup',json={'email':email,'password':'password123'})).json()
        return result['id'], {'Authorization':'Bearer '+result['token']}

    async def grant(self,bid,email='editor@example.com',role='editor',accept=True):
        uid,headers=await self.account(email);owner=self.headers
        await self.ok('POST',f'/boards/{bid}/sharing',201,json={'email':email,'role':role,'reviewed_revision':0,'content_reviewed':True})
        if accept:
            self.headers=headers;await self.ok('POST',f'/boards/{bid}/invitation/accept');self.headers=owner
        return uid,headers

    async def test_invite_accept_revoke_and_identity_boundaries(self):
        bid=(await self.board())['id'];owner=self.headers
        uid,editor=await self.grant(bid,accept=False)
        self.headers=editor
        await self.ok('GET',f'/boards/{bid}',404)
        inbox=await self.ok('GET','/shared-boards');self.assertEqual(inbox['items'][0]['invitation_status'],'pending')
        await self.ok('POST',f'/boards/{bid}/invitation/accept')
        self.assertEqual((await self.ok('GET',f'/boards/{bid}'))['role'],'editor')
        self.headers=owner;await self.ok('DELETE',f'/boards/{bid}/sharing/{uid}')
        self.headers=editor
        for path in (f'/boards/{bid}',f'/boards/{bid}/scene',f'/boards/{bid}/revisions'):
            await self.ok('GET',path,404)
        await self.ok('POST',f'/boards/{bid}/invitation/accept',404)
        self.headers=owner
        await self.ok('POST',f'/boards/{bid}/sharing',201,json={'email':'editor@example.com','role':'viewer','reviewed_revision':0,'content_reviewed':True})
        self.headers=editor;await self.ok('GET',f'/boards/{bid}',404)
        await self.ok('DELETE',f'/boards/{bid}/invitation')
        self.headers=owner
        owner_id=(await self.ok('GET','/auth/me'))['id']
        await self.ok('PATCH',f'/boards/{bid}/sharing/{owner_id}',422,json={'role':'viewer'})
        await self.ok('POST',f'/boards/{bid}/sharing',422,json={'email':'owner@example.com','role':'viewer','reviewed_revision':0,'content_reviewed':True})

    async def test_owner_editor_viewer_matrix_and_cas(self):
        bid=(await self.board())['id'];owner=self.headers
        uid,editor=await self.grant(bid)
        _,viewer=await self.grant(bid,'viewer@example.com','viewer')
        self.headers=editor
        await self.save(bid)
        await self.ok('PATCH',f'/boards/{bid}',403,json={'title':'stolen'})
        await self.ok('PATCH',f'/boards/{bid}/sharing/{uid}',403,json={'role':'viewer'})
        self.headers=owner;await self.save(bid,0,status=409)
        self.headers=viewer
        for path in (f'/boards/{bid}',f'/boards/{bid}/scene',f'/boards/{bid}/revisions',f'/boards/{bid}/revisions/1'):
            await self.ok('GET',path)
        await self.save(bid,1,status=403)
        await self.ok('POST',f'/boards/{bid}/conversations/new',403)
        await self.ok('POST',f'/boards/{bid}/generations',403,json={'request_key':'viewer_blocked','prompt':'chat','mode':'chat'})
        await self.ok('POST',f'/boards/{bid}/selection/resolve',403,json={'expected_revision':1,'element_ids':['shape']})
        await self.ok('POST',f'/boards/{bid}/revisions/1/restore',403,json={'expected_revision':1})
        self.headers=editor
        await self.ok('POST',f'/boards/{bid}/revisions/1/restore',json={'expected_revision':1})
        self.headers=owner;await self.ok('PATCH',f'/boards/{bid}/sharing/{uid}',json={'role':'viewer'})
        self.headers=editor;await self.save(bid,2,status=403)

    async def test_source_files_rag_citations_and_personal_history_stay_private(self):
        project=await self.project();bid=(await self.board(project_id=project['id']))['id']
        did=self.document(pid=project['id'],content='PRIVATE worksheet values and extracted passage')
        await self.ok('POST',f'/boards/{bid}/resources',201,json={'document_id':did})
        cid=(await self.ok('POST',f'/boards/{bid}/conversations/new',201))['conversation_id']
        owner=self.headers;_,editor=await self.grant(bid)
        from app.canvas_generation_models import CanvasArtifact, ArtifactVersion
        with self.sessions() as db:
            owner_id=db.scalar(select(User.id).where(User.email=='owner@example.com'))
            db.add(CanvasArtifact(id='private-proposal',owner_id=owner_id,board_id=bid,request_key='private_unaccepted'))
            db.flush();db.add(ArtifactVersion(artifact_id='private-proposal',version=1,engine='B',content_json=json.dumps({'private':'PRIVATE extracted worksheet data'})));db.commit()
        self.headers=editor
        self.assertEqual((await self.ok('GET',f'/boards/{bid}/artifacts'))['items'],[])
        await self.ok('GET',f'/boards/{bid}/artifacts/private-proposal',404)
        await self.ok('POST',f'/boards/{bid}/artifacts/private-proposal/duplicate',404,json={'request_key':'forged_private_copy','version':1})
        self.assertEqual((await self.ok('GET',f'/boards/{bid}/conversations'))['items'],[])
        await self.ok('GET',f'/conversations/{cid}',404)
        for path in (f'/documents/{did}',f'/documents/{did}/download',f'/projects/{project["id"]}',f'/boards?workspace_id={self.wid}',f'/boards/{bid}/resource-library',f'/boards/{bid}/resource-library/available',f'/boards/{bid}/resource-library/image/1',f'/boards/{bid}/resources'):
            response=await self.client.get(path,headers=self.headers)
            self.assertIn(response.status_code,(403,404),response.text)
            self.assertNotIn('PRIVATE',response.text)
        reference={'kind':'document','source_id':did,'fingerprint':'0'*64}
        await self.ok('POST',f'/boards/{bid}/resource-library/preview',403,json=reference)
        await self.ok('POST',f'/boards/{bid}/resource-library',403,json={'kind':'document','source_id':did})
        await self.ok('DELETE',f'/boards/{bid}/resources/{did}',403)
        await self.ok('POST',f'/boards/{bid}/selection/resolve',403,json={'expected_revision':0,'resources':[reference]})
        ownchat=await self.ok('POST',f'/boards/{bid}/conversations/new',201)
        self.assertEqual(len((await self.ok('GET',f'/boards/{bid}/conversations'))['items']),1)
        from app.database import Message, Attachment
        with self.sessions() as db:
            db.add(Message(conversation_id=ownchat['conversation_id'],role='user',content='Private editor chat',attachments=[Attachment(attachment_name='EDITOR_PRIVATE_IMAGE.png',attachment_mime='image/png',attachment_size=1,attachment_data='AA==')]))
            db.commit()
        self.headers=owner
        available=await self.ok('GET',f'/boards/{bid}/resource-library/available')
        self.assertNotIn('EDITOR_PRIVATE_IMAGE',json.dumps(available))
        self.assertEqual((await self.ok('GET',f'/boards/{bid}/conversations'))['items'][0]['conversation_id'],cid)
        await self.ok('GET',f'/conversations/{ownchat["conversation_id"]}',404)

    async def test_stale_content_review_no_silent_history_release(self):
        bid=(await self.board())['id'];await self.account('pending@example.com')
        await self.save(bid)
        payload={'email':'pending@example.com','role':'viewer','reviewed_revision':0,'content_reviewed':True}
        await self.ok('POST',f'/boards/{bid}/sharing',409,json=payload)
        await self.ok('POST',f'/boards/{bid}/sharing',422,json={**payload,'reviewed_revision':1,'content_reviewed':False})
        await self.ok('POST',f'/boards/{bid}/sharing',201,json={**payload,'reviewed_revision':1})

    async def test_shared_editor_uses_personal_key_quota_and_usage(self):
        bid=(await self.board())['id'];owner=self.headers
        uid,editor=await self.grant(bid);self.headers=editor
        cid=(await self.ok('POST',f'/boards/{bid}/conversations/new',201))['conversation_id']
        with self.sessions() as db:
            user=db.get(User,uid);user.encrypted_api_key=gemini.cipher().encrypt(b'editor-private-fake-key').decode();db.commit()
        result=await self.ok('POST',f'/boards/{bid}/generations',201,json={'request_key':'own_key_generation','prompt':'Explain collaboration','mode':'chat','conversation_id':cid})
        keys=[]
        class Fake:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*_):pass
            async def generate_content(self,**kwargs):return SimpleNamespace(text='Personal response',usage_metadata=SimpleNamespace(prompt_token_count=10,candidates_token_count=3,total_token_count=13))
        def client(key):keys.append(key);return Fake()
        model={'id':'gemini-test-flash','input_token_limit':100000,'output_token_limit':8192,'tier':'free','pricing_checked_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
        with patch.object(gemini,'client_for',side_effect=client),patch.object(gemini,'selected_model',AsyncMock(return_value=model)):
            self.assertEqual(generation.claim(self.sessions),result['id']);await generation.execute(result['id'],self.sessions)
        self.assertEqual(keys,['editor-private-fake-key'])
        with self.sessions() as db:
            job=db.get(Job,result['id']);self.assertEqual(job.status,'completed',job.error);usage=db.get(Usage,job.usage_id);self.assertEqual(usage.user_id,uid)
        self.headers=owner;await self.ok('GET',f'/boards/{bid}/generations/{result["id"]}',404)
        self.headers=editor
        self.headers=owner;await self.ok('PATCH',f'/boards/{bid}/sharing/{uid}',json={'role':'viewer'})
        self.headers=editor;await self.ok('GET',f'/boards/{bid}/generations/{result["id"]}',403)

    async def test_sse_rechecks_revocation_expiry_and_logout(self):
        bid=(await self.board())['id'];owner=self.headers
        uid,editor=await self.grant(bid);self.headers=editor
        with self.sessions() as db:
            db.get(User,uid).encrypted_api_key=gemini.cipher().encrypt(b'sse-fake-key').decode();db.commit()
        result=await self.ok('POST',f'/boards/{bid}/generations',201,json={'request_key':'sse_revocation','prompt':'Explain','mode':'chat'})
        from app import canvas_generation_api
        class Capture:
            def patch(self,*args):return lambda fn:fn
            def include_router(self,router):self.router=router
        capture=Capture();canvas_generation_api.register(capture,main.user_from_token,main.db_session)
        endpoint=next(r.endpoint for r in capture.router.routes if getattr(r,'path','')=='/boards/{bid}/generations/{jid}/events')
        request=Request({'type':'http','method':'GET','path':'/','headers':[(b'authorization',editor['Authorization'].encode())]})
        request.is_disconnected=AsyncMock(return_value=False)
        with self.sessions() as db:
            response=endpoint(bid,result['id'],request,0,db.get(User,uid),db)
            iterator=response.body_iterator
            await anext(iterator)
            with self.sessions() as fresh:fresh.delete(fresh.get(BoardMember,(bid,uid)));fresh.commit()
            remaining=''.join([frame async for frame in iterator])
            self.assertIn('access_revoked',remaining)
        # Authentication expiry is checked even while board membership remains.
        import jwt
        expired=jwt.encode({'sub':str(uid),'exp':time.time()-1},main.SECRET,algorithm='HS256')
        expired_request=Request({'type':'http','headers':[(b'authorization',('Bearer '+expired).encode())]})
        with self.sessions() as db:self.assertFalse(browser.stream_valid(expired_request,uid,db,main.SECRET))

    async def test_cookie_transition_csrf_expiry_logout_and_old_bearer(self):
        auth=self.headers;trusted={'Origin':'http://test','X-Kumuta-CSRF':'1'}
        self.assertEqual((await self.client.get('/auth/session')).json(),{'authenticated':False})
        response=await self.client.post('/auth/browser-session',headers=auth)
        self.assertEqual(response.status_code,403)
        response=await self.client.post('/auth/browser-session',headers={**auth,**trusted})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('HttpOnly',response.headers['set-cookie']);self.assertIn('SameSite=lax',response.headers['set-cookie'])
        self.assertTrue((await self.client.get('/auth/me')).json()['browser_session'])
        self.assertTrue((await self.client.get('/auth/session')).json()['authenticated'])
        await self.ok('POST','/workspaces',403,json={'name':'CSRF blocked'})
        response=await self.client.post('/workspaces',headers=trusted,json={'name':'Cookie session'})
        self.assertEqual(response.status_code,201,response.text)
        response=await self.client.post('/auth/logout',headers={**trusted,'Origin':'https://attacker.example'})
        self.assertEqual(response.status_code,403)
        response=await self.client.post('/auth/logout',headers=trusted);self.assertEqual(response.status_code,200)
        self.assertEqual((await self.client.get('/auth/me',headers=auth)).status_code,401)
        self.client.cookies.clear()
        self.assertEqual((await self.client.get('/auth/me',headers=auth)).status_code,401)

    async def test_cookie_account_switch_invalidates_old_session(self):
        auth=self.headers;trusted={'Origin':'http://test','X-Kumuta-CSRF':'1'}
        await self.client.post('/auth/browser-session',headers={**auth,**trusted})
        cookie=self.client.cookies.get(browser.COOKIE)
        uid,other=await self.account('switch@example.com')
        await self.client.post('/auth/browser-session',headers={**other,**trusted})
        self.assertEqual((await self.client.get('/auth/me',headers=auth)).json()['id'],uid)
        with self.sessions() as db:
            self.assertFalse(browser.valid(browser.digest(cookie),1,db))
            current=db.get(browser.BrowserSession,browser.digest(self.client.cookies.get(browser.COOKIE)));current.expires_at=0;db.commit()
        self.assertEqual((await self.client.get('/auth/me',headers=other)).status_code,401)
