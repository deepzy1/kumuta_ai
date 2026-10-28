"""Disposable SQLite + fake Gemini; no real keys, quota, or user data."""
import asyncio
import json
import unittest
import httpx
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
import test_boards as fixture
from test_boards import element, scene
from app import canvas_generation as service, gemini
from app.canvas_generation_models import GenerationJob as Job, GenerationEvent as Event, ArtifactVersion as Version
from app.canvas_generation_schemas import route_engine, validate_generated
from app.database import Usage, User, migrate, engine

DIAGRAM={'nodes':[{'id':'a','type':'rectangle','x':0,'y':0,'width':160,'height':70,'text':'Start'},
                  {'id':'b','type':'rectangle','x':260,'y':0,'width':160,'height':70,'text':'End'}], 'edges':[{'from':'a','to':'b'}]}
WIDGET={'version':1,'title':'Illustrative calculator','blocks':[{'type':'calculator','operation':'sum',
        'inputs':[{'label':'Count','min':0,'max':100,'step':1,'value':3}]}]}


class GenerationSchemaTests(unittest.TestCase):
    def test_routing_and_strict_model_output(self):
        for prompt,engine in [('architecture diagram','A'),('mind map','A'),('calculator','B'),('dashboard','B'),('interactive simulation','C')]:
            self.assertEqual(route_engine(prompt),engine)
        self.assertEqual(route_engine('chart','A'),'A')
        validate_generated('A',json.dumps(DIAGRAM));validate_generated('B',json.dumps(WIDGET))
        for output in [{**DIAGRAM,'javascript':'alert(1)'},{'nodes':DIAGRAM['nodes']*2,'edges':[]},
                       {**DIAGRAM,'edges':[{'from':'a','to':'missing'}]}]:
            with self.assertRaises(ValueError):validate_generated('A',json.dumps(output))
        for output in [{**WIDGET,'html':'<script>'},{**WIDGET,'blocks':[{'type':'html','html':'<img onerror=alert(1)>'}]},
                       {**WIDGET,'blocks':[{'type':'markdown','text':'[unsafe](javascript:alert(1))'}]},
                       {**WIDGET,'blocks':[{'type':'chart','labels':['a'],'series':[{'name':'x','values':[float('nan')]}]}]}]:
            with self.assertRaises(ValueError):validate_generated('B',json.dumps(output))
        with self.assertRaises(ValueError):validate_generated('C','{}')


class GenerationSDKTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_serializes_canvas_json_without_full_quickui_schema(self):
        from google import genai
        for name in ('gemini-3.5-flash-lite','gemini-3.6-flash'):
            with self.subTest(model=name):
                requests=[]
                def handler(request):
                    body=json.loads(request.content);requests.append(body)
                    config=body['generationConfig']
                    self.assertEqual(config['responseMimeType'],'application/json')
                    self.assertNotIn('responseJsonSchema',config)
                    self.assertNotIn('responseSchema',config)
                    self.assertNotIn('tools',body)
                    instruction=body['systemInstruction']['parts'][0]['text']
                    self.assertIn('columns(string[]),rows(cell[][])',instruction)
                    self.assertIn('operation(sum|product|compound|loan|formula)',instruction)
                    self.assertIn('arithmetic results using x1..x6',instruction)
                    self.assertIn('Never execute code',instruction)
                    self.assertIn('No markdown/diagram blocks',instruction)
                    return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'text':json.dumps(WIDGET)}]}}],
                        'usageMetadata':{'promptTokenCount':77,'candidatesTokenCount':23,'totalTokenCount':100}})
                config,system=service.generation_setup({'id':name,'output_token_limit':8192},'B')
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                    async with genai.Client(api_key='fake-sdk-key',http_options=gemini.types.HttpOptions(
                        httpx_async_client=http,retry_options=gemini.types.HttpRetryOptions(attempts=1))).aio as client:
                        result=await client.models.generate_content(model=name,contents='Build a calculator',config=config)
                self.assertEqual(len(requests),1)
                self.assertEqual(validate_generated('B',result.text)['payload']['blocks'][0]['operation'],'sum')
                self.assertEqual(config.system_instruction,system)

    async def test_native_schema_and_strict_validation_still_apply(self):
        config,system=service.generation_setup({'id':'gemini-3.6-flash'},'A')
        self.assertIsNone(config.response_json_schema)
        self.assertIn('Use 1-100 nodes and 0-200 edges', system)
        self.assertEqual(config.response_mime_type,'application/json')
        self.assertTrue(system.startswith(service.SYSTEM))
        with self.assertRaises(ValueError):service.generation_setup({'id':'gemini-3.6-flash'},'C')

    async def test_rejected_sdk_request_is_not_automatically_retried(self):
        from google import genai
        from google.genai.errors import ClientError
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(400,json={'error':{'code':400,'status':'INVALID_ARGUMENT','message':'Invalid generation configuration'}})
        config,_=service.generation_setup({'id':'gemini-3.6-flash'},'B')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with genai.Client(api_key='fake-sdk-key',http_options=gemini.types.HttpOptions(
                httpx_async_client=http,retry_options=gemini.types.HttpRetryOptions(attempts=1))).aio as client:
                with self.assertRaises(ClientError):
                    await client.models.generate_content(model='gemini-3.6-flash',contents='Calculator',config=config)
        self.assertEqual(len(calls),1)


class GenerationAPITests(unittest.IsolatedAsyncioTestCase):
    ok=fixture.BoardAPITests.ok
    board=fixture.BoardAPITests.board
    save=fixture.BoardAPITests.save

    async def asyncSetUp(self):
        await fixture.BoardAPITests.asyncSetUp(self)
        patch.object(service,'OPENUI_ENABLED',False).start()
        self.response=DIAGRAM;self.failure=None;self.block=None;self.calls=0
        self.model={'id':'gemini-test-flash','input_token_limit':100000,'output_token_limit':8192,'tier':'free','pricing_checked_at':datetime.now(timezone.utc).isoformat()}
        patch.object(gemini,'selected_model',AsyncMock(return_value=self.model)).start()
        owner=self
        class Fake:
            aio=None
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*_):pass
            async def generate_content(self,**kwargs):
                owner.calls+=1
                # A write succeeds here only if no application transaction is held.
                with owner.sessions() as db:
                    db.execute(update(User).where(User.email=='owner@example.com').values(preferred_model='gemini-test-flash'));db.commit()
                if owner.block:await owner.block.wait()
                if owner.failure:raise owner.failure
                return SimpleNamespace(text=owner.response if isinstance(owner.response,str) else json.dumps(owner.response),usage_metadata=SimpleNamespace(prompt_token_count=77,candidates_token_count=23,total_token_count=105))
            async def generate_content_stream(self,**kwargs):
                response=await self.generate_content(**kwargs)
                async def chunks():
                    yield response
                return chunks()
        self.fake=patch.object(gemini,'client_for',side_effect=lambda _:Fake()).start()
        with self.sessions() as db:
            u=db.scalar(select(User).where(User.email=='owner@example.com'));u.encrypted_api_key=gemini.cipher().encrypt(b'private-fake-key').decode();db.commit()
        self.bid=(await self.board())['id']

    async def asyncTearDown(self):
        await fixture.BoardAPITests.asyncTearDown(self)

    async def create(self,**values):
        return await self.ok('POST',f'/boards/{self.bid}/generations',201,json={'request_key':'request_123','prompt':'Create a diagram','engine':'auto',**values})

    async def finish(self):
        jid=service.claim(self.sessions)
        self.assertIsNotNone(jid)
        await service.execute(jid,self.sessions)
        return await self.ok('GET',f'/boards/{self.bid}/generations/{jid}')

    async def artifact(self,aid):
        return await self.ok('GET',f'/boards/{self.bid}/artifacts/{aid}')

    def added(self,aid,version=1,engine='A'):
        return [element(f'{aid}_v{version}-anchor',width=540,height=380)] if engine=='B' else [element(f'{aid}_v{version}-node',width=160,height=70)]

    async def place(self,aid,revision=0,version=1,operation='insert',engine='A',status=200):
        return await self.ok('POST',f'/boards/{self.bid}/artifacts/{aid}/placement',status,json={
            'expected_revision':revision,'version':version,'operation':operation,
            'elements':[] if operation=='remove' else self.added(aid,version,engine)})

    async def test_board_chats_are_durable_scoped_and_do_not_change_scene(self):
        first=await self.ok('POST',f'/boards/{self.bid}/conversations/new',201)
        second=await self.ok('POST',f'/boards/{self.bid}/conversations/new',201)
        before=await self.ok('GET',f'/boards/{self.bid}/scene')
        self.response=WIDGET
        a=await self.create(conversation_id=first['conversation_id'],engine='B',prompt='NAND calculator')
        await self.finish()
        b=await self.create(request_key='second_chat_request',conversation_id=second['conversation_id'],engine='B',prompt='OR calculator')
        await self.finish()
        self.assertNotEqual(a['artifact_id'],b['artifact_id'])
        for cid,jid in [(first['conversation_id'],a['id']),(second['conversation_id'],b['id'])]:
            page=await self.ok('GET',f'/boards/{self.bid}/generations?conversation_id={cid}')
            self.assertEqual([j['id'] for j in page['items']],[jid])
        self.assertEqual(await self.ok('GET',f'/boards/{self.bid}/scene'),before)
        chats=(await self.ok('GET',f'/boards/{self.bid}/conversations'))['items']
        self.assertEqual({c['title'] for c in chats},{'NAND calculator','OR calculator'})
        other=(await self.board())['id']
        await self.ok('POST',f'/boards/{other}/generations',404,json={'request_key':'cross_board_request','prompt':'Create form','conversation_id':first['conversation_id']})
        await self.ok('GET',f'/boards/{other}/generations?conversation_id={first["conversation_id"]}',404)

    async def test_durable_states_accounting_idempotency_and_reconnect(self):
        job=await self.create();self.assertEqual(job['status'],'queued')
        self.assertEqual((await self.create())['id'],job['id'])
        done=await self.finish();self.assertEqual(done['status'],'completed');self.assertEqual(self.calls,1)
        self.assertEqual(done['usage'],{'input_tokens':77,'output_tokens':23,'total_tokens':105,'estimated':0,'status':'complete'})
        with self.sessions() as db:
            self.assertEqual(list(db.scalars(select(Event.status).where(Event.job_id==job['id']).order_by(Event.sequence))),['queued','planning','generating','validating','rendering','completed'])
        for _ in range(2):
            r=await self.client.get(f'/boards/{self.bid}/generations/{job["id"]}/events?after=3',headers=self.headers)
            self.assertEqual(r.status_code,200);self.assertIn('event: completed',r.text);self.assertNotIn('event: planning',r.text)
        self.assertEqual((await self.create())['id'],job['id']);self.assertEqual(self.calls,1)
        artifact=await self.artifact(job['artifact_id']);self.assertIsNone(artifact['placement']);self.assertEqual(artifact['versions'][0]['version'],1)
        await self.ok('POST',f'/boards/{self.bid}/generations',409,json={'request_key':'request_123','prompt':'different prompt'})

    async def test_artifact_insert_replace_revert_duplicate_remove_and_scene_conflict(self):
        job=await self.create();await self.finish();aid=job['artifact_id']
        await self.save(self.bid,value=scene(element('unrelated')))
        await self.place(aid,0,status=409)
        first=await self.place(aid,1);self.assertEqual(first['revision'],2)
        again=await self.place(aid,1);self.assertTrue(again['idempotent']);self.assertEqual(again['revision'],2)
        self.assertIn('unrelated',[e['id'] for e in first['scene']['elements']])
        await self.create(request_key='regenerate_123',artifact_id=aid);await self.finish()
        self.assertEqual((await self.artifact(aid))['placement']['version'],1)
        second=await self.place(aid,2,2,'replace');self.assertEqual(second['revision'],3)
        reverted=await self.place(aid,3,1,'replace');self.assertEqual(reverted['artifact']['placement']['version'],1)
        duplicate=await self.ok('POST',f'/boards/{self.bid}/artifacts/{aid}/duplicate',201,json={'request_key':'duplicate_123','version':1})
        repeated=await self.ok('POST',f'/boards/{self.bid}/artifacts/{aid}/duplicate',201,json={'request_key':'duplicate_123','version':1})
        self.assertEqual(duplicate['id'],repeated['id'])
        await self.place(duplicate['id'],4)
        removed=await self.place(aid,5,operation='remove');self.assertTrue(removed['artifact']['placement']['removed'])
        self.assertEqual(len((await self.artifact(aid))['versions']),2)
        self.assertEqual(self.calls,2)

    async def test_structured_state_reload_and_failed_regeneration_keeps_last_good(self):
        self.response=WIDGET
        j=await self.create(engine='B');await self.finish();aid=j['artifact_id']
        inserted=await self.place(aid,engine='B');value=inserted['scene'];value['artifacts'][0]['state']={'0':[42]}
        await self.save(self.bid,1,value)
        self.response={'html':'<script>parent.fetch("/settings")</script>'}
        await self.create(request_key='invalid_regen',artifact_id=aid,engine='B');done=await self.finish()
        self.assertEqual(done['status'],'failed');self.assertEqual(done['usage']['estimated'],0)
        a=await self.artifact(aid);self.assertEqual(len(a['versions']),1);self.assertEqual(a['placement']['version'],1)
        saved=await self.ok('GET',f'/boards/{self.bid}/scene');self.assertEqual(saved['scene']['artifacts'][0]['state'],{'0':[42.0]})
        await self.place(aid,2,operation='remove',engine='B')
        self.assertEqual(self.calls,2)

    async def test_cancel_queued_and_inflight_does_not_publish_or_retry(self):
        job=await self.create();jid=job['id']
        await self.ok('POST',f'/boards/{self.bid}/generations/{jid}/cancel')
        self.assertIsNone(service.claim(self.sessions));self.assertEqual(self.calls,0)
        job=await self.create(request_key='inflight_123');jid=service.claim(self.sessions)
        self.block=asyncio.Event();task=asyncio.create_task(service.execute(jid,self.sessions))
        while not self.calls:await asyncio.sleep(.01)
        await self.ok('POST',f'/boards/{self.bid}/generations/{jid}/cancel')
        await task
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/generations/{jid}'))['status'],'cancelled')
        self.assertFalse((await self.artifact(job['artifact_id']))['versions']);self.assertEqual(self.calls,1)

    async def test_provider_failure_timeout_and_unknown_usage(self):
        class Quota(Exception):code=429
        self.failure=Quota()
        await self.create();failed=await self.finish();self.assertEqual(failed['status'],'failed');self.assertIn('quota',failed['error'])
        self.assertEqual(failed['usage']['estimated'],1)
        self.failure=TimeoutError()
        await self.create(request_key='timeout_123');timed=await self.finish();self.assertEqual(timed['status'],'timed_out')
        self.assertEqual(self.calls,2)

    async def test_restart_only_resumes_queued_and_marks_ambiguous_expired(self):
        job=await self.create();jid=service.claim(self.sessions)
        with self.sessions() as db:
            row=db.get(Job,jid);row.deadline=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();row.provider_started_at=row.created_at;db.commit()
        self.assertIsNone(service.claim(self.sessions))
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/generations/{jid}'))['status'],'timed_out')
        await self.create(request_key='queued_restart');await self.finish();self.assertEqual(self.calls,1)

    async def test_limits_and_custom_gate_do_not_call_provider(self):
        await self.ok('POST',f'/boards/{self.bid}/generations',422,json={'request_key':'empty_123','prompt':'   '})
        for prompt,engine in [('Custom HTML simulation','auto'),('Something custom','C')]:
            await self.ok('POST',f'/boards/{self.bid}/generations',422,json={'request_key':'custom_123','prompt':prompt,'engine':engine})
        await self.create()
        await self.ok('POST',f'/boards/{self.bid}/generations',429,json={'request_key':'parallel_123','prompt':'another diagram'})
        self.assertEqual(self.calls,0)
        jid=service.claim(self.sessions)
        self.assertIsNone(service.claim(self.sessions))
        await service.execute(jid,self.sessions)
        with patch.object(service,'DAILY_JOBS',1):
            await self.ok('POST',f'/boards/{self.bid}/generations',429,json={'request_key':'quota_123','prompt':'another diagram'})
        with patch.object(service,'DAILY_JOBS',0):
            await self.create(request_key='unlimited_local_test')
        self.assertEqual(self.calls,1)  # Creating a queued job does not call the provider.

    async def test_every_endpoint_owner_authorization_archive_and_secret_isolation(self):
        job=await self.create();await self.finish();aid=job['artifact_id'];jid=job['id']
        paths=[('GET','/generations',None),('POST','/generations',{'request_key':'new_12345','prompt':'diagram'}),
               ('GET',f'/generations/{jid}',None),('GET',f'/generations/{jid}/events',None),('POST',f'/generations/{jid}/cancel',None),
               ('GET','/artifacts',None),('GET',f'/artifacts/{aid}',None),('POST',f'/artifacts/{aid}/placement',{'expected_revision':0,'version':1}),
               ('POST',f'/artifacts/{aid}/duplicate',{'request_key':'copy_12345','version':1})]
        paths.append(('POST',f'/artifacts/{aid}/versions/1/render',{'status':'ready'}))
        owner=self.headers
        r=await self.client.post('/auth/signup',json={'email':'stranger@example.com','password':'password123'})
        self.headers={'Authorization':'Bearer '+r.json()['token']}
        for method,path,body in paths:
            await self.ok(method,f'/boards/{self.bid}{path}',404,**({'json':body} if body else {}))
            unauth=await self.client.request(method,f'/boards/{self.bid}{path}',**({'json':body} if body else {}));self.assertEqual(unauth.status_code,401)
        self.headers=owner
        serialized=json.dumps(await self.artifact(aid));self.assertNotIn('private-fake-key',serialized);self.assertNotIn('Bearer',serialized)
        await self.ok('PATCH',f'/boards/{self.bid}',json={'status':'archived'})
        await self.place(aid,status=409)
        await self.ok('POST',f'/boards/{self.bid}/generations',409,json={'request_key':'archived_123','prompt':'diagram'})

    async def test_immutable_versions_and_unsafe_placement_rollback(self):
        j=await self.create();await self.finish();aid=j['artifact_id']
        with self.sessions() as db:
            with self.assertRaises(IntegrityError):
                db.execute(update(Version).where(Version.artifact_id==aid).values(content_json='{}'));db.commit()
            db.rollback()
        for added in [[element('unrelated')],[{**self.added(aid)[0],'link':'javascript:alert(1)'}],
                      [{**self.added(aid)[0],'type':'embeddable'}]]:
            await self.ok('POST',f'/boards/{self.bid}/artifacts/{aid}/placement',422,json={'expected_revision':0,'version':1,'elements':added})
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],0)

    async def test_scene_restore_native_delete_undo_and_render_reports(self):
        j=await self.create();await self.finish();aid=j['artifact_id']
        await self.place(aid)
        await self.create(request_key='second_version',artifact_id=aid);await self.finish()
        await self.place(aid,1,2,'replace')
        await self.ok('POST',f'/boards/{self.bid}/revisions/1/restore',json={'expected_revision':2})
        self.assertEqual((await self.artifact(aid))['placement']['version'],1)
        await self.place(aid,3,2,'replace')
        s=await self.ok('GET',f'/boards/{self.bid}/scene');s['scene']['elements'][0]['isDeleted']=True
        await self.save(self.bid,4,s['scene']);self.assertTrue((await self.artifact(aid))['placement']['removed'])
        s['scene']['elements'][0]['isDeleted']=False
        await self.save(self.bid,5,s['scene']);self.assertFalse((await self.artifact(aid))['placement']['removed'])
        await self.ok('POST',f'/boards/{self.bid}/artifacts/{aid}/versions/2/render',json={'status':'ready'})
        self.assertEqual((await self.artifact(aid))['versions'][0]['rendering_status'],'ready')
        await self.ok('POST',f'/boards/{self.bid}/artifacts/{aid}/versions/2/render',422,json={'status':'ready','token':'forged'})
        self.assertEqual(self.calls,2)

    async def test_concurrent_idempotent_submissions_and_global_capacity(self):
        payload={'request_key':'concurrent_key','prompt':'diagram'}
        results=await asyncio.gather(*(self.client.post(f'/boards/{self.bid}/generations',headers=self.headers,json=payload) for _ in range(2)))
        self.assertEqual([r.status_code for r in results],[201,201]);self.assertEqual(results[0].json()['id'],results[1].json()['id'])
        jid=service.claim(self.sessions)
        with patch.object(service,'MAX_ACTIVE',1):self.assertIsNone(service.claim(self.sessions))
        await service.execute(jid,self.sessions);self.assertEqual(self.calls,1)
        with patch.object(service,'MAX_ARTIFACT_BYTES',0):
            await self.ok('POST',f'/boards/{self.bid}/artifacts/{results[0].json()["artifact_id"]}/duplicate',413,json={'request_key':'over_budget','version':1})

    async def test_revoked_key_or_paid_consent_is_rechecked_before_dispatch(self):
        await self.create()
        async def changed(_):
            with self.sessions() as db:
                db.execute(update(User).where(User.email=='owner@example.com').values(encrypted_api_key=None));db.commit()
            return self.model
        with patch.object(gemini,'selected_model',side_effect=changed):
            done=await self.finish()
        self.assertEqual(done['status'],'failed');self.assertEqual(self.calls,0)
        self.assertIn('settings changed',done['error'])
