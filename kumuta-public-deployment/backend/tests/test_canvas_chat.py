"""D7-4.2: offline chat, routing, model snapshot, shared uploads and persistence."""
import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import func, select, update
import test_canvas_generation as gen
from app import canvas_generation as service, gemini
from app.canvas_generation_schemas import route_mode
from app.canvas_generation_models import CanvasArtifact
from app.database import Conversation, Message, User, now

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=')


class ModeRoutingTests(unittest.TestCase):
    def test_modes_and_conversational_intent(self):
        for prompt,expected in [('Explain a dashboard','T'),('What is a diagram?','T'),('Hello there','T'),('Write a function to sort a table','T'),('Create an architecture diagram','A'),('Build an interactive dashboard','B'),('Create a comparison table','B'),('Can you create a diagram from this image?','A'),('What does this image show?','T'),('Can you explain a diagram?','T'),('Could you create a dashboard?','B'),('Make a Markdown table comparing algorithms','T')]:
            self.assertEqual(route_mode(prompt),expected,prompt)
        for mode,engine in [('chat','T'),('diagram','A'),('ui','B')]:
            self.assertEqual(route_mode('Explain this',mode),engine)
        self.assertEqual(route_mode('Make it orange','auto','B'),'B')
        self.assertEqual(route_mode('Add a database','auto','A'),'A')


class CanvasChatTests(unittest.IsolatedAsyncioTestCase):
    ok=gen.GenerationAPITests.ok
    board=gen.GenerationAPITests.board
    create=gen.GenerationAPITests.create
    finish=gen.GenerationAPITests.finish
    artifact=gen.GenerationAPITests.artifact
    asyncSetUp=gen.GenerationAPITests.asyncSetUp
    asyncTearDown=gen.GenerationAPITests.asyncTearDown

    async def chat(self):
        return (await self.ok('POST',f'/boards/{self.bid}/conversations/new',201))['conversation_id']

    async def test_text_history_and_reload_without_artifact_generation(self):
        cid=await self.chat(); self.response='## Answer\n\n| A | B |\n|---|---|\n|1|2|\n\n```python\nprint(1)\n```'
        first=await self.create(mode='auto',conversation_id=cid,prompt='Explain a dashboard')
        self.assertEqual(first['engine'],'T');done=await self.finish()
        self.assertEqual(done['reply_text'],self.response);self.assertIsNone(done['version'])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CanvasArtifact)),0)
            self.assertEqual(db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id==cid)),2)
        await self.create(mode='chat',conversation_id=cid,prompt='Explain that again',request_key='follow_up_123')
        captured=[]
        class Fake:
            def __init__(self): self.aio=self; self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*_):pass
            async def generate_content(self,**kwargs):
                captured.append(kwargs);return SimpleNamespace(text='Follow-up answer',usage_metadata=None)
        with patch.object(gemini,'client_for',return_value=Fake()):second=await self.finish()
        self.assertEqual(len(captured),1)
        self.assertIn(done['reply_text'],str(captured[0]['contents']))
        self.assertIsNone(captured[0]['config'].response_mime_type)
        restored=await self.ok('GET',f'/boards/{self.bid}/generations/{second["id"]}')
        self.assertEqual(restored['reply_text'],'Follow-up answer')
        other=await self.chat();await self.create(mode='chat',conversation_id=other,request_key='isolated_chat_123')
        captured.clear()
        with patch.object(gemini,'client_for',return_value=Fake()):await self.finish()
        self.assertNotIn('Follow-up answer',str(captured[0]['contents']))
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],0)

    async def test_all_artifact_modes_and_auto_follow_up_keep_preview_lifecycle(self):
        cid=await self.chat()
        for index,mode,engine,response in [(0,'diagram','A',gen.DIAGRAM),(1,'ui','B',gen.WIDGET),(2,'auto','B',gen.WIDGET)]:
            self.response=response
            with patch.object(service,'OPENUI_ENABLED',True):
                if engine=='B':
                    from test_canvas_openui import PROGRAM
                    self.response=PROGRAM
                row=await self.create(mode=mode,conversation_id=cid,prompt='Make it orange' if index==2 else 'Create a dashboard',request_key=f'mode_request_{index}')
                self.assertEqual(row['engine'],engine);done=await self.finish()
            self.assertEqual(done['status'],'completed',done);self.assertTrue(done['reply_text'])
            artifact=await self.artifact(done['artifact_id']);self.assertIsNone(artifact['placement']);self.assertEqual(len(artifact['versions']),1)
            self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],0)

    async def test_model_is_pinned_while_next_selection_changes_and_mode_is_private(self):
        with self.sessions() as db:
            db.execute(update(User).values(preferred_model='gemini-test-pro'));db.commit()
        cid=await self.chat();row=await self.create(mode='chat',model='gemini-test-pro',conversation_id=cid)
        with self.sessions() as db:
            db.execute(update(User).values(preferred_model='gemini-test-flash'));db.commit()
        seen=[]
        async def resolve(user):
            seen.append(user.preferred_model);return {**self.model,'id':user.preferred_model}
        self.response='Pinned reply'
        client=self.fake.side_effect('unused-test-key')
        captured=AsyncMock(wraps=client.generate_content);client.generate_content=captured
        with patch.object(gemini,'selected_model',side_effect=resolve),patch.object(gemini,'client_for',return_value=client):done=await self.finish()
        self.assertEqual(captured.call_args.kwargs['model'],'gemini-test-pro')
        self.assertEqual(seen,['gemini-test-pro']);self.assertEqual(done['model'],'gemini-test-pro')
        await self.ok('PATCH','/settings/canvas',json={'mode':'diagram'})
        with self.sessions() as db:self.assertEqual(db.scalar(select(User.canvas_generation_mode)),'diagram')
        await self.ok('PATCH','/settings/canvas',422,json={'mode':'C'})
        await self.ok('POST',f'/boards/{self.bid}/generations',409,json={'mode':'chat','model':'tampered-model','request_key':'bad_model_123','prompt':'Explain that'})

    async def test_shared_image_upload_is_idempotent_and_forwarded_for_every_mode(self):
        cid=await self.chat()
        for index,mode in enumerate(['chat','diagram','ui','auto']):
            data={'request_key':f'image_request_{index}','prompt':'Analyze this image' if mode in ('chat','auto') else 'Create a diagram from this image','mode':mode,'conversation_id':cid}
            async def upload(raw=PNG):
                return await self.ok('POST',f'/boards/{self.bid}/generations',201,data={'request':json.dumps(data)},files=[('attachments',('reference.png',raw,'image/png'))])
            row=await upload();same=await upload();self.assertEqual(row['id'],same['id']);self.assertEqual(len(row['attachments']),1)
            with self.sessions() as db:
                message=db.get(Message,row['user_message_id']);self.assertEqual(len(message.attachments),1)
                self.assertEqual(base64.b64decode(message.attachments[0].attachment_data),PNG)
            captured=[]
            class Fake:
                def __init__(self):self.aio=self;self.models=self
                async def __aenter__(self):return self
                async def __aexit__(self,*_):pass
                async def generate_content(self,**kwargs):
                    captured.append(kwargs)
                    response='Image understood' if row['engine']=='T' else json.dumps(gen.DIAGRAM if row['engine']=='A' else gen.WIDGET)
                    return SimpleNamespace(text=response,usage_metadata=None)
            with patch.object(gemini,'client_for',return_value=Fake()):done=await self.finish()
            self.assertEqual(done['status'],'completed',done)
            parts=captured[0]['contents'][-1].parts
            self.assertTrue(any(p.inline_data and p.inline_data.data==PNG for p in parts))
            a=row['attachments'][0]
            response=await self.client.get(f'/conversations/{cid}/attachments/{row["user_message_id"]}/{a["id"]}',headers=self.headers)
            self.assertEqual(response.content,PNG)

    async def test_bad_images_capabilities_and_api_failures_are_bounded(self):
        cid=await self.chat();path=f'/boards/{self.bid}/generations';data={'request_key':'invalid_image_123','prompt':'Explain this image','mode':'chat','conversation_id':cid}
        for raw,mime,status in [(b'fake','image/png',415),(b'%PDF-invalid','application/pdf',415),(b'x'*(8*1024*1024+1),'image/png',413)]:
            await self.ok('POST',path,status,data={'request':json.dumps(data)},files=[('attachments',('input',raw,mime))])
        row=await self.ok('POST',path,201,data={'request':json.dumps(data)},files=[('attachments',('input.png',PNG,'image/png'))])
        with patch.object(gemini,'selected_model',AsyncMock(return_value={**self.model,'supports_images':False})):
            done=await self.finish()
        self.assertEqual(done['status'],'failed');self.assertIn('does not support image',done['error']);self.assertEqual(self.calls,0)
        from test_api import ProviderError
        self.failure=ProviderError(503)
        await self.create(mode='chat',request_key='failure_request_123',conversation_id=cid)
        done=await self.finish();self.assertEqual(done['status'],'failed');self.assertEqual(self.calls,1)
        self.assertEqual(done['diagnostic']['category'],'provider_unavailable')
        self.assertIsNone(done['reply_text'])

    async def test_shared_conversation_generation_locks_and_stale_lease_recovery(self):
        cid=await self.chat()
        row=await self.create(mode='chat',conversation_id=cid)
        await self.ok('POST',f'/conversations/{cid}/messages',409,data={'text':'Another chat surface'})
        await self.ok('POST',f'/boards/{self.bid}/generations/{row["id"]}/cancel')
        with self.sessions() as db:
            conversation=db.get(Conversation,cid);conversation.generation_id='main-chat-lease';conversation.generation_started=now();db.commit()
        await self.ok('POST',f'/boards/{self.bid}/generations',409,json={'request_key':'locked_chat_123','prompt':'Explain this','mode':'chat','conversation_id':cid})
        with self.sessions() as db:
            db.get(Conversation,cid).generation_started='2000-01-01T00:00:00+00:00';db.commit()
        row=await self.create(request_key='recovered_chat_123',mode='chat',conversation_id=cid)
        self.assertEqual(row['status'],'queued')
