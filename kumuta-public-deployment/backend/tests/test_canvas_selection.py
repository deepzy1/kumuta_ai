"""D7-5 selection isolation, budgets, durable provenance and atomic approval."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_boards import element, scene
import test_canvas_generation as gen
from app import gemini
from app.canvas_selection import Bounds, SelectionRequest, bounds


class GeometryTests(unittest.TestCase):
    def test_limits_and_rotated_bounds(self):
        b=bounds(element(width=100,height=20,angle=1.5707963267948966))
        self.assertAlmostEqual(b['width'],20);self.assertAlmostEqual(b['height'],100)
        for value in [dict(x=float('nan'),y=0,width=2,height=2),dict(x=0,y=0,width=12001,height=2)]:
            with self.assertRaises(ValueError):Bounds(**value)
        for value in [{},{'element_ids':['a','a']},{'element_ids':['a'],'region':{'x':0,'y':0,'width':10,'height':10}}]:
            with self.assertRaises(ValueError):SelectionRequest(expected_revision=0,**value)


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    ok=gen.GenerationAPITests.ok
    board=gen.GenerationAPITests.board
    save=gen.GenerationAPITests.save
    create=gen.GenerationAPITests.create
    finish=gen.GenerationAPITests.finish
    artifact=gen.GenerationAPITests.artifact
    added=gen.GenerationAPITests.added
    place=gen.GenerationAPITests.place
    asyncSetUp=gen.GenerationAPITests.asyncSetUp
    asyncTearDown=gen.GenerationAPITests.asyncTearDown

    async def setup_scene(self):
        await self.save(self.bid,value=scene(element('node'),element('other',x=1000),element('arrow',type='arrow',x=120,width=400,height=1,points=[[0,0],[400,0]],startBinding={'elementId':'node','focus':0,'gap':1},endBinding={'elementId':'other','focus':0,'gap':1})))

    async def resolve(self,**kwargs):
        return await self.ok('POST',f'/boards/{self.bid}/selection/resolve',json={'expected_revision':1,'element_ids':['node'],**kwargs})

    async def test_native_region_and_connector_context_excludes_other_content(self):
        await self.setup_scene();context=await self.resolve(element_ids=['node','arrow'])
        self.assertEqual(context['element_ids'],['arrow','node']);self.assertEqual(self.calls,0)
        arrow=next(e for e in context['native'] if e['type']=='arrow')
        self.assertEqual(arrow['startBinding']['elementId'],'node');self.assertNotIn('endBinding',arrow)
        self.assertNotIn('other',json.dumps(context));self.assertFalse(context['visual_attached'])
        context=await self.resolve(element_ids=[],region={'x':0,'y':0,'width':115,'height':100})
        self.assertEqual(context['element_ids'],['node']);self.assertEqual(context['kind'],'region');self.assertEqual(context['bounds']['width'],115)
        await self.resolve_reject(422,element_ids=['forged'])
        await self.resolve_reject(409,expected_revision=0)
        other=(await self.board())['id']
        await self.ok('POST',f'/boards/{other}/selection/resolve',422,json={'expected_revision':0,'element_ids':['node']})
        second=(await self.client.post('/auth/signup',json={'email':'selection-other@example.com','password':'password123'})).json()
        r=await self.client.post(f'/boards/{self.bid}/selection/resolve',headers={'Authorization':'Bearer '+second['token']},json={'expected_revision':1,'element_ids':['node']})
        self.assertEqual(r.status_code,404)

    async def resolve_reject(self,status,**kwargs):
        return await self.ok('POST',f'/boards/{self.bid}/selection/resolve',status,json={'expected_revision':1,'element_ids':['node'],**kwargs})

    async def test_text_response_has_provenance_and_only_selected_provider_context(self):
        await self.setup_scene();cid=(await self.ok('POST',f'/boards/{self.bid}/conversations/new',201))['conversation_id']
        self.response='Selected explanation'
        row=await self.create(mode='ui',conversation_id=cid,selection={'expected_revision':1,'element_ids':['node'],'action':'explain'})
        self.assertEqual(row['engine'],'T');captured=[]
        class Fake:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*_):pass
            async def generate_content(self,**kwargs):captured.append(kwargs);return SimpleNamespace(text='Selected explanation',usage_metadata=None)
        with patch.object(gemini,'client_for',return_value=Fake()):done=await self.finish()
        self.assertEqual(done['status'],'completed',done);self.assertEqual(done['reply_text'],'Selected explanation');self.assertIsNotNone(done['assistant_message_id'])
        payload=json.loads(captured[0]['contents'][-1].parts[0].text)
        self.assertNotIn('other',json.dumps(payload));self.assertNotIn('recent_artifacts',payload);self.assertNotIn('board_title',payload)
        self.assertEqual(payload['selection']['element_ids'],['node'])
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],1)
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/generations/{row["id"]}'))['selection']['element_ids'],['node'])

    async def test_atomic_modify_preview_replay_cas_and_history(self):
        await self.setup_scene()
        row=await self.create(mode='auto',selection={'expected_revision':1,'element_ids':['node'],'action':'modify'})
        done=await self.finish();self.assertEqual(done['status'],'completed',done)
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],1)
        art=await self.artifact(row['artifact_id']);self.assertEqual(art['versions'][0]['selection']['element_ids'],['node'])
        await self.place(row['artifact_id'],revision=0,operation='selection',status=409)
        saved=await self.place(row['artifact_id'],revision=1,operation='selection')
        self.assertEqual(saved['revision'],2)
        self.assertTrue(next(e for e in saved['scene']['elements'] if e['id']=='node')['isDeleted'])
        self.assertFalse(next(e for e in saved['scene']['elements'] if e['id']=='other')['isDeleted'])
        replay=await self.place(row['artifact_id'],revision=1,operation='selection');self.assertTrue(replay['idempotent']);self.assertEqual(replay['revision'],2)
        await self.ok('POST',f'/boards/{self.bid}/revisions/1/restore',json={'expected_revision':2})
        restored=await self.ok('GET',f'/boards/{self.bid}/scene');self.assertEqual(restored['revision'],3)
        self.assertFalse(next(e for e in restored['scene']['elements'] if e['id']=='node')['isDeleted'])

    async def test_changed_selection_and_locked_content_do_not_accept(self):
        await self.setup_scene();row=await self.create(selection={'expected_revision':1,'element_ids':['node'],'action':'modify'});await self.finish()
        await self.save(self.bid,expected=1,value=scene(element('node',x=50),element('other',x=1000)))
        await self.place(row['artifact_id'],revision=2,operation='selection',status=409)
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],2)
        row=await self.create(request_key='locked_selection',selection={'expected_revision':2,'element_ids':['node'],'action':'modify'})
        await self.finish()
        # Changed geometry/state is rejected even before lock replacement checks.
        await self.save(self.bid,expected=2,value=scene(element('node',x=50,locked=True),element('other',x=1000)))
        await self.place(row['artifact_id'],revision=3,operation='selection',status=409)

    async def test_widget_and_mixed_state_are_authoritative_and_isolated(self):
        self.response=gen.WIDGET;row=await self.create(engine='B');await self.finish();saved=await self.place(row['artifact_id'],engine='B')
        state=saved['scene'];state['elements'].append(element('native',x=2000));state['artifacts'][0]['state']={'0':[7]}
        state['elements'].append(element('second-anchor',x=3000,width=540,height=380))
        state['artifacts'].append({**state['artifacts'][0],'id':'manual-second','anchor_id':'second-anchor','state':{'0':[11]}})
        await self.save(self.bid,expected=1,value=state)
        anchor=state['artifacts'][0]['anchor_id'];context=await self.resolve(expected_revision=2,element_ids=[anchor,'native'])
        self.assertEqual(context['widgets'][0]['state'],{'0':[7]});self.assertEqual(context['native'][0]['id'],'native');self.assertNotIn('manual-second',json.dumps(context))
        multiple=await self.resolve(expected_revision=2,element_ids=[anchor,'second-anchor'])
        self.assertEqual([w['state'] for w in multiple['widgets']],[{'0':[7]},{'0':[11]}])
        self.assertEqual(context['artifact_refs'],[{'artifact_id':row['artifact_id'],'version':1}])
        self.response=gen.WIDGET
        change=await self.create(request_key='widget_change_123',mode='auto',prompt='Simplify this calculator',selection={'expected_revision':2,'element_ids':[anchor],'action':'modify'})
        self.assertEqual(change['engine'],'B');await self.finish()
        modified=await self.place(change['artifact_id'],revision=2,operation='selection',engine='B')
        self.assertEqual(len(modified['scene']['artifacts']),3) # tombstoned definition retained for native undo
        self.assertEqual(next(a for a in modified['scene']['artifacts'] if a['id']==row['artifact_id'])['state'],{'0':[7]})

    async def test_budgets_stale_dispatch_and_cancel_make_zero_provider_calls(self):
        await self.save(self.bid,value=scene(*[element(f'n{i}',x=i) for i in range(121)]))
        await self.resolve_reject(413,element_ids=[],region={'x':0,'y':0,'width':500,'height':100})
        await self.save(self.bid,expected=1,value=scene(element('node',type='text',text='x'*33000)))
        await self.resolve_reject(413,expected_revision=2)
        await self.save(self.bid,expected=2,value=scene(element('node')))
        row=await self.create(selection={'expected_revision':3,'element_ids':['node'],'action':'explain'})
        await self.save(self.bid,expected=3,value=scene(element('node',x=50)))
        done=await self.finish();self.assertEqual(done['status'],'failed');self.assertEqual(self.calls,0)
        row=await self.create(request_key='cancel_selection',selection={'expected_revision':4,'element_ids':['node'],'action':'explain'})
        await self.ok('POST',f'/boards/{self.bid}/generations/{row["id"]}/cancel')
        self.assertEqual(self.calls,0)

    async def test_regeneration_retains_identity_and_rejects_other_artifact_targets(self):
        await self.setup_scene()
        request={'expected_revision':1,'element_ids':['node'],'action':'modify'}
        first=await self.create(selection=request);await self.finish()
        second=await self.create(request_key='selection_regenerate',artifact_id=first['artifact_id'],selection=request)
        result=await self.finish();self.assertEqual(result['version'],2)
        self.assertEqual(first['artifact_id'],second['artifact_id'])
        art=await self.artifact(first['artifact_id']);self.assertEqual(len(art['versions']),2)
        await self.ok('POST',f'/boards/{self.bid}/generations',422,json={'request_key':'forged_target_123','prompt':'Improve this', 'artifact_id':first['artifact_id'],'selection':{**request,'element_ids':['other']}})

    async def test_visual_bytes_consent_and_provider_failure_preserve_scene(self):
        from test_canvas_chat import PNG
        from test_api import ProviderError
        request={'request_key':'selection_visual_123','prompt':'Explain this','mode':'chat','selection':{'expected_revision':1,'element_ids':['node'],'action':'explain','visual':True}}
        await self.setup_scene();cid=(await self.ok('POST',f'/boards/{self.bid}/conversations/new',201))['conversation_id'];request['conversation_id']=cid
        await self.ok('POST',f'/boards/{self.bid}/generations',422,json=request)
        request['selection']['visual']=False
        await self.ok('POST',f'/boards/{self.bid}/generations',422,data={'request':json.dumps(request)},files=[('attachments',('region.png',PNG,'image/png'))])
        request['selection']['visual']=True
        row=await self.ok('POST',f'/boards/{self.bid}/generations',201,data={'request':json.dumps(request)},files=[('attachments',('region.png',PNG,'image/png'))])
        self.assertTrue(row['selection']['visual_attached'])
        captured=[]
        class Fake:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*_):pass
            async def generate_content(self,**kwargs):captured.append(kwargs);return SimpleNamespace(text='Image answer',usage_metadata=None)
        with patch.object(gemini,'client_for',return_value=Fake()):done=await self.finish()
        self.assertEqual(done['status'],'completed',done)
        self.assertTrue(any(p.inline_data and p.inline_data.data==PNG for p in captured[0]['contents'][-1].parts))
        self.failure=ProviderError(503)
        await self.create(request_key='selection_failure_123',selection={'expected_revision':1,'element_ids':['node'],'action':'modify'})
        failed=await self.finish();self.assertEqual(failed['status'],'failed');self.assertEqual(self.calls,1)
        self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],1)

    async def test_selected_context_obeys_model_budget_before_provider_dispatch(self):
        await self.setup_scene();self.model['input_token_limit']=10
        await self.create(selection={'expected_revision':1,'element_ids':['node'],'action':'explain'})
        failed=await self.finish();self.assertEqual(failed['status'],'failed');self.assertEqual(self.calls,0)
        self.assertIn('budget',failed['error'])
