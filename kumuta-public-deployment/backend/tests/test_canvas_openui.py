"""Restricted OpenUI programs, actual SDK requests and disposable lifecycle."""
import asyncio
import json
import unittest
from unittest.mock import patch
import httpx
from app import canvas_generation as service, gemini
from app.canvas_generation_schemas import validate_generated
from app.canvas_openui import FORMAT, LEGACY, REGISTRY, parse_program, registry_prompt
import test_canvas_generation as gen
from test_canvas_generation import WIDGET

PROGRAM = 'root = Stack("Illustrative calculator", [calc]); calc = Calculator("", "sum", [{"label":"Count","value":3,"min":0,"max":100,"step":1}]);'

class OpenUIParserTests(unittest.TestCase):
    def test_forward_refs_and_all_registered_components(self):
        self.assertEqual(parse_program(PROGRAM)['blocks'][0]['inputs'][0]['value'],3)
        source='''root = Stack("Illustrative dashboard", [Text("Explanation", "Supplied evidence only"),
          Table("Data", ["Name","Value"], [["A",2]]), Cards("KPI", [{"label":"Total","value":2}]),
          Chart("Trend", "line", ["Jan"], [{"name":"Value","values":[2]}]),
          Timeline("Steps", [{"when":"First","title":"Learn"}]),
          Calculator("Try", "product", [{"label":"A","value":2}]),
          Progress("Progress", [{"label":"Learning","value":25}]),
          Checklist("Practice", [{"text":"Try it"}]),
          Form("Answer", [{"kind":"select","label":"Choice","options":["Yes","No"],"value":"Yes"}], "Save")]);'''
        result=validate_generated('B',source,FORMAT)
        self.assertEqual(result['format'],FORMAT)
        self.assertEqual(len(result['payload']['blocks']),len(REGISTRY))
        for name in REGISTRY:self.assertIn(name+'(',registry_prompt())

    def test_malformed_unsafe_unknown_unused_and_cycles_fail_closed(self):
        cases=[PROGRAM[:-2], PROGRAM+'root = Stack("dup", []);',
            'root = Stack("", [Unknown("x")]);', 'root = Stack("", [x]); x = x;',
            'root = Stack("", [a]); a = b; b = a;', 'root = Stack("", [missing]);',
            'root = Stack("", [Calculator("", "eval", [])]);',
            'root = Stack("", [Cards("", [{"label":"x","onClick":"fetch()"}])]);',
            'root = Stack("", [Cards("", [{"label":"x","label":"y"}])]);',
            'root = Stack("", [Cards("", [{"__proto__":{}}])]);',
            'root = Stack("", [@Query("https://example.com")]);',
            'root = Stack("", [Form("", $state)]);',
            'root = Stack("", [Calculator("", "sum", [{"label":"x","value":1+2}])]);',
            'root = Stack("", [Cards("", [{"label":window.localStorage}])]);',
            'root = Stack("", [Chart("", "bar", ["a"], [{"name":"x","values":[1e999]}])]);',
            PROGRAM+' unused = Table("", [], []);', PROGRAM+' unused = Unknown();',
            '```openui\n'+PROGRAM+'\n```', json.dumps(WIDGET),
            'root = Stack("", [Stack("", [])]);']
        for source in cases:
            with self.subTest(source=source[:80]),self.assertRaises((ValueError,TypeError)):
                validate_generated('B',source,FORMAT)

    def test_budgets_legacy_and_truncated_output(self):
        for source in ['x'*100001,'root = '+'['*40+'0'+']'*40,'root=Stack("",[]);'*130]:
            with self.assertRaises(ValueError):parse_program(source)
        for n in range(PROGRAM.index('Calculator'),len(PROGRAM)-2):
            with self.assertRaises(ValueError):parse_program(PROGRAM[:n])
        self.assertEqual(validate_generated('B',json.dumps(WIDGET))['payload']['version'],1)

class OpenUISDKTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_plain_text_no_schema_or_tools(self):
        from google import genai
        for model in ['gemini-3.5-flash-lite','gemini-3.6-flash']:
            requests=[]
            def handler(request):
                body=json.loads(request.content);requests.append(body)
                cfg=body['generationConfig'];self.assertEqual(cfg['responseMimeType'],'text/plain')
                self.assertNotIn('responseJsonSchema',cfg);self.assertNotIn('tools',body)
                self.assertIn('restricted library',body['systemInstruction']['parts'][0]['text'])
                return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'text':PROGRAM}]}}]})
            config,_=service.generation_setup({'id':model},'B',FORMAT)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                async with genai.Client(api_key='fake',http_options=gemini.types.HttpOptions(httpx_async_client=http,retry_options=gemini.types.HttpRetryOptions(attempts=1))).aio as client:
                    result=await client.models.generate_content(model=model,contents='calculator',config=config)
            self.assertEqual(validate_generated('B',result.text,FORMAT)['format'],FORMAT)
            self.assertEqual(len(requests),1)

    async def test_real_sdk_stream_framing_and_incremental_parser(self):
        from google import genai
        from app.canvas_openui import partial_program
        pieces=['root=Stack("Stream",[a,b]);a=Cards("",[{"label":"A"}]);','b=Progress("",[{"label":"B","value":3}]);']
        requests=[]
        def handler(request):
            requests.append(request)
            frames=[]
            for piece in pieces:
                frames.append('data: '+json.dumps({'candidates':[{'content':{'role':'model','parts':[{'text':piece}]}}]})+'\n\n')
            return httpx.Response(200,headers={'Content-Type':'text/event-stream'},text=''.join(frames))
        config,_=service.generation_setup({'id':'gemini-3.6-flash'},'B',FORMAT)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with genai.Client(api_key='fake',http_options=gemini.types.HttpOptions(httpx_async_client=http,retry_options=gemini.types.HttpRetryOptions(attempts=1))).aio as client:
                stream=await client.models.generate_content_stream(model='gemini-3.6-flash',contents='dashboard',config=config)
                answer='';sizes=[]
                async for chunk in stream:
                    answer+=chunk.text or ''
                    sizes.append(len(partial_program(answer)['blocks']))
        self.assertEqual(sizes,[1,2]);self.assertEqual(len(requests),1)
        self.assertIn('streamGenerateContent',str(requests[0].url))
        self.assertEqual(len(validate_generated('B',answer,FORMAT)['payload']['blocks']),2)

class OpenUIAPITests(unittest.IsolatedAsyncioTestCase):
    ok=gen.GenerationAPITests.ok;board=gen.GenerationAPITests.board;save=gen.GenerationAPITests.save;create=gen.GenerationAPITests.create;finish=gen.GenerationAPITests.finish
    artifact=gen.GenerationAPITests.artifact;added=gen.GenerationAPITests.added;place=gen.GenerationAPITests.place
    async def asyncSetUp(self):
        await gen.GenerationAPITests.asyncSetUp(self);patch.object(service,'OPENUI_ENABLED',True).start();self.response=PROGRAM
    asyncTearDown=gen.GenerationAPITests.asyncTearDown

    async def test_preference_idempotency_reload_versions_duplicate_and_legacy(self):
        job=await self.create(engine='B');self.assertEqual(job['output_format'],FORMAT)
        with patch.object(service,'OPENUI_ENABLED',False):self.assertEqual((await self.create(engine='B'))['id'],job['id'])
        self.assertEqual((await self.finish())['status'],'completed');aid=job['artifact_id']
        self.assertEqual((await self.artifact(aid))['versions'][0]['content']['format'],FORMAT)
        inserted=await self.place(aid,engine='B');value=inserted['scene'];value['artifacts'][0]['state']={'0':[42]}
        await self.save(self.bid,1,value);saved=await self.ok('GET',f'/boards/{self.bid}/scene')
        self.assertEqual(saved['scene']['artifacts'][0]['format'],FORMAT)
        self.assertEqual(saved['scene']['artifacts'][0]['state'],{'0':[42]})
        self.response=WIDGET
        legacy=await self.create(engine='B',request_key='legacy_request',artifact_id=aid,output_format=LEGACY)
        self.assertEqual(legacy['output_format'],LEGACY);await self.finish()
        self.assertEqual((await self.artifact(aid))['placement']['version'],1)
        await self.place(aid,2,2,'replace',engine='B');await self.place(aid,3,1,'replace',engine='B')
        copy=await self.ok('POST',f'/boards/{self.bid}/artifacts/{aid}/duplicate',201,json={'request_key':'copy_openui','version':1})
        self.assertEqual(copy['versions'][0]['content']['format'],FORMAT);await self.place(copy['id'],4,engine='B')
        self.assertEqual(len((await self.ok('GET',f'/boards/{self.bid}/scene'))['scene']['artifacts']),2)
        for _ in range(2):await self.client.get(f'/boards/{self.bid}/generations/{job["id"]}/events',headers=self.headers)
        self.assertEqual(self.calls,2)

    async def test_disabled_queue_and_explicit_legacy(self):
        j=await self.create(engine='B')
        with patch.object(service,'OPENUI_ENABLED',False):
            self.assertEqual((await self.finish())['status'],'failed');self.assertEqual(self.calls,0)
            await self.ok('POST',f'/boards/{self.bid}/generations',422,json={'prompt':'calculator','engine':'B','output_format':FORMAT,'request_key':'disabled_openui'})
            self.response=WIDGET;job=await self.create(engine='B',request_key='disabled_legacy')
            self.assertEqual(job['output_format'],LEGACY);self.assertEqual((await self.finish())['status'],'completed')
        self.assertEqual(self.calls,1);self.assertFalse((await self.artifact(j['artifact_id']))['versions'])

    async def test_invalid_no_retry_or_publish(self):
        self.response=PROGRAM[:-10];j=await self.create(engine='B');done=await self.finish()
        self.assertEqual(done['status'],'failed');self.assertIn('Legacy JSON',done['error'])
        self.assertEqual(self.calls,1);self.assertFalse((await self.artifact(j['artifact_id']))['versions'])
        self.assertEqual(done['usage']['input_tokens'],77)

    async def test_cancel_quota_and_other_owner(self):
        job=await self.create(engine='B');jid=service.claim(self.sessions);self.block=asyncio.Event()
        task=asyncio.create_task(service.execute(jid,self.sessions))
        while not self.calls:await asyncio.sleep(.01)
        await self.ok('POST',f'/boards/{self.bid}/generations/{jid}/cancel');await task
        self.assertFalse((await self.artifact(job['artifact_id']))['versions']);self.assertEqual(self.calls,1)
        with patch.object(service,'DAILY_JOBS',1):await self.ok('POST',f'/boards/{self.bid}/generations',429,json={'request_key':'over_openui_quota','prompt':'calculator','engine':'B'})
        r=await self.client.post('/auth/signup',json={'email':'openui-stranger@example.com','password':'password123'})
        self.headers={'Authorization':'Bearer '+r.json()['token']}
        await self.ok('GET',f'/boards/{self.bid}/artifacts/{job["artifact_id"]}',404)

    async def test_bounded_stream_partial_recovery_and_final_failure(self):
        from types import SimpleNamespace
        from sqlalchemy import select
        from app.canvas_generation_models import GenerationEvent as Event
        from app.canvas_openui import partial_program
        source='root=Stack("Streaming",[one,two]); one=Cards("KPI",[{"label":"Count","value":3}]);'
        self.assertEqual(len(partial_program(source)['blocks']),1)
        self.assertIsNone(partial_program('root=Stack("Incomplete'))
        release=asyncio.Event();owner=self
        class Stream:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def generate_content_stream(self,**kwargs):
                owner.calls+=1
                async def chunks():
                    yield SimpleNamespace(text=source,usage_metadata=None)
                    await release.wait()
                    yield SimpleNamespace(text='two=Progress("",[{"label":"Done","value":25}]);',usage_metadata=None)
                    yield SimpleNamespace(text='@Unsafe();',usage_metadata=None)
                return chunks()
        job=await self.create(engine='B');jid=service.claim(self.sessions)
        with patch.object(gemini,'client_for',side_effect=lambda _:Stream()):
            task=asyncio.create_task(service.execute(jid,self.sessions))
            for _ in range(100):
                state=await self.ok('GET',f'/boards/{self.bid}/generations/{jid}')
                if state['partial_preview']:break
                await asyncio.sleep(.01)
            self.assertEqual(state['status'],'generating')
            self.assertEqual(len(state['partial_preview']['payload']['blocks']),1)
            self.assertFalse((await self.artifact(job['artifact_id']))['versions'])
            # Reads/reconnection use the durable preview without another dispatch.
            self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/generations/{jid}'))['partial_preview'],state['partial_preview'])
            release.set();await task
        final=await self.ok('GET',f'/boards/{self.bid}/generations/{jid}')
        self.assertEqual(final['status'],'failed');self.assertIsNone(final['partial_preview'])
        self.assertFalse((await self.artifact(job['artifact_id']))['versions']);self.assertEqual(self.calls,1)
        with self.sessions() as db:
            previews=list(db.scalars(select(Event.preview_json).where(Event.job_id==jid,Event.preview_json.is_not(None))))
            self.assertTrue(0<len(previews)<=4);self.assertTrue(all(len(p.encode())<=24000 for p in previews))

    async def test_stream_byte_and_chunk_budgets_close_without_publication(self):
        from types import SimpleNamespace
        owner=self
        for mode in ('bytes','chunks'):
            closed=[]
            class Stream:
                def __init__(self):self.aio=self;self.models=self
                async def __aenter__(self):return self
                async def __aexit__(self,*args):pass
                async def generate_content_stream(self,**kwargs):
                    owner.calls+=1
                    async def chunks():
                        try:
                            for _ in range(1 if mode=='bytes' else 4097):
                                yield SimpleNamespace(text='x'*100001 if mode=='bytes' else '',usage_metadata=None)
                        finally:closed.append(True)
                    return chunks()
            job=await self.create(engine='B',request_key='bounded_'+mode)
            with patch.object(gemini,'client_for',side_effect=lambda _:Stream()):done=await self.finish()
            self.assertEqual(done['status'],'failed');self.assertIn('bounded stream limit',done['error'])
            self.assertEqual(closed,[True]);self.assertFalse((await self.artifact(job['artifact_id']))['versions'])
        self.assertEqual(self.calls,2)

    async def test_cancel_during_partial_stream_closes_and_clears_preview(self):
        from types import SimpleNamespace
        release=asyncio.Event();closed=[];owner=self
        class Stream:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def generate_content_stream(self,**kwargs):
                owner.calls+=1
                async def chunks():
                    try:
                        yield SimpleNamespace(text='root=Stack("Partial",[a,b]);a=Cards("",[{"label":"A"}]);',usage_metadata=None)
                        await release.wait()
                    finally:closed.append(True)
                return chunks()
        job=await self.create(engine='B');jid=service.claim(self.sessions)
        with patch.object(gemini,'client_for',side_effect=lambda _:Stream()):
            task=asyncio.create_task(service.execute(jid,self.sessions))
            for _ in range(100):
                state=await self.ok('GET',f'/boards/{self.bid}/generations/{jid}')
                if state['partial_preview']:break
                await asyncio.sleep(.01)
            self.assertTrue(state['partial_preview'])
            await self.ok('POST',f'/boards/{self.bid}/generations/{jid}/cancel');await task
        self.assertEqual(closed,[True]);self.assertEqual(self.calls,1)
        self.assertIsNone((await self.ok('GET',f'/boards/{self.bid}/generations/{jid}'))['partial_preview'])
        self.assertFalse((await self.artifact(job['artifact_id']))['versions'])
