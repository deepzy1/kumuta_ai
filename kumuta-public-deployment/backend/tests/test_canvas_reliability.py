"""Reliability boundaries, fake SDK/provider only; no live quota."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from google import genai
from app import canvas_generation as service, gemini
from app.canvas_diagnostics import failure_code
from app.canvas_openui import FORMAT, LEGACY
from app.canvas_generation_schemas import validate_generated
import test_canvas_generation as gen
from test_canvas_openui import PROGRAM

class RequestMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_model_native_legacy_openui_and_chat_sdk_requests(self):
        model = {'id':'gemini-3.6-flash'}
        for engine, fmt, output in [('A',LEGACY,json.dumps(gen.DIAGRAM)),('B',LEGACY,json.dumps(gen.WIDGET)),('B',FORMAT,PROGRAM),('chat',None,'Connected')]:
            calls=[]
            def handler(request):
                body=json.loads(request.content);calls.append(body)
                self.assertNotIn('responseJsonSchema',body['generationConfig'])
                self.assertNotIn('responseSchema',body['generationConfig'])
                self.assertNotIn('tools',body)
                return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'text':output}]},'finishReason':'STOP'}]})
            config = gemini.generation_config(model) if engine=='chat' else service.generation_setup(model,engine,fmt)[0]
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                async with genai.Client(api_key='fake',http_options=gemini.types.HttpOptions(httpx_async_client=http,retry_options=gemini.types.HttpRetryOptions(attempts=1))).aio as client:
                    result=await client.models.generate_content(model=model['id'],contents='Illustrative example',config=config)
            self.assertEqual(len(calls),1)
            if engine!='chat':validate_generated(engine,result.text,fmt)

    def test_timeout_and_internal_errors_are_not_provider_busy(self):
        self.assertEqual(failure_code(httpx.ReadTimeout('private detail'),'generating'),'timeout')
        self.assertEqual(failure_code(RuntimeError('private detail'),'rendering'),'internal')

class ReliabilityAPITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=gen.GenerationAPITests.asyncSetUp
    asyncTearDown=gen.GenerationAPITests.asyncTearDown
    ok=gen.GenerationAPITests.ok
    board=gen.GenerationAPITests.board
    save=gen.GenerationAPITests.save
    create=gen.GenerationAPITests.create
    finish=gen.GenerationAPITests.finish
    artifact=gen.GenerationAPITests.artifact
    added=gen.GenerationAPITests.added
    place=gen.GenerationAPITests.place
    async def test_error_categories_are_durable_one_call_and_sanitized(self):
        for code, category in [('429','quota_exhausted'),('503','provider_unavailable'),('400','unsupported_request'),('403','authentication'),('404','unsupported_model')]:
            class ProviderFailure(Exception): pass
            self.failure=ProviderFailure('SECRET prompt key URL');self.failure.code=code
            job=await self.create(request_key='failure_'+code,engine='B')
            done=await self.finish()
            self.assertEqual(done['diagnostic']['category'],category)
            self.assertEqual(done['diagnostic']['stage'],'generating')
            self.assertEqual(done['diagnostic']['code'],code)
            self.assertFalse(done['diagnostic']['historical_inference'])
            self.assertNotIn('SECRET',done['error']);self.assertIsNotNone(done['usage'])
            self.assertFalse((await self.artifact(job['artifact_id']))['versions'])
        self.assertEqual(self.calls,5)

    async def test_all_widget_scenarios_complete_in_both_formats(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
        from openui_fixtures import openui_fixture
        from app.quickui import Specification
        scenarios = {
          'calculator':gen.WIDGET['blocks'],
          'chart':[{'type':'chart','labels':['A'],'series':[{'name':'Count','values':[2]}]}],
          'table':[{'type':'table','columns':['Name','Value'],'rows':[['A',2]]}],
          'dashboard':[{'type':'cards','items':[{'label':'Count','value':2}]},{'type':'progress','items':[{'label':'Done','value':20}]}],
          'form':[{'type':'form','fields':[{'label':'Name','value':''}]}],
        }
        with patch.object(service,'OPENUI_ENABLED',True):
            for name,blocks in scenarios.items():
                spec=Specification.model_validate({'title':'Illustrative '+name,'blocks':blocks}).model_dump()
                for fmt in (LEGACY,FORMAT):
                    self.response=openui_fixture(spec) if fmt==FORMAT else spec
                    await self.create(engine='B',output_format=fmt,request_key=name+'_'+fmt)
                    self.assertEqual((await self.finish())['status'],'completed')
        self.assertEqual(self.calls,10)

    async def test_truncation_rejects_even_valid_prefix_and_keeps_accepted_version(self):
        await self.create();completed=await self.finish();aid=completed['artifact_id']
        await self.place(aid)
        owner=self
        class Fake:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def generate_content(self,**kwargs):
                owner.calls+=1
                return SimpleNamespace(text=json.dumps(gen.DIAGRAM),usage_metadata=SimpleNamespace(prompt_token_count=70,candidates_token_count=80,total_token_count=150),candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')])
        await self.create(request_key='truncated_request',artifact_id=aid)
        with patch.object(gemini,'client_for',side_effect=lambda _:Fake()):done=await self.finish()
        self.assertEqual(done['diagnostic']['category'],'truncated_output')
        artifact=await self.artifact(aid)
        self.assertEqual(len(artifact['versions']),1);self.assertEqual(artifact['placement']['version'],1)
        self.assertEqual(self.calls,2);self.assertFalse(done['usage']['estimated'])

    async def test_stream_finish_reason_survives_final_metadata_only_chunk(self):
        owner=self
        class Fake:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def generate_content_stream(self,**kwargs):
                owner.calls+=1
                async def chunks():
                    yield SimpleNamespace(text=PROGRAM,usage_metadata=None,candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')])
                    yield SimpleNamespace(text='',usage_metadata=None,candidates=[])
                return chunks()
        with patch.object(service,'OPENUI_ENABLED',True):
            await self.create(engine='B',output_format=FORMAT)
            with patch.object(gemini,'client_for',side_effect=lambda _:Fake()):done=await self.finish()
        self.assertEqual(done['diagnostic']['code'],'MAX_TOKENS');self.assertEqual(self.calls,1)

    async def test_optional_preview_parser_cannot_abort_valid_final_program(self):
        self.response=PROGRAM
        with patch.object(service,'OPENUI_ENABLED',True):
            await self.create(engine='B',output_format=FORMAT)
            with patch.object(service,'partial_program',side_effect=ValueError('incomplete optional preview')):
                done=await self.finish()
        self.assertEqual(done['status'],'completed');self.assertEqual(self.calls,1)

    async def test_unsupported_component_has_actionable_registry_error(self):
        self.response='root=Stack("Example",[PieChart("Unsupported")]);'
        with patch.object(service,'OPENUI_ENABLED',True):
            await self.create(engine='B',output_format=FORMAT)
            done=await self.finish()
        self.assertEqual(done['diagnostic']['code'],'unsupported_component')
        self.assertIn('Chart (bar/line)',done['error']);self.assertEqual(self.calls,1)
