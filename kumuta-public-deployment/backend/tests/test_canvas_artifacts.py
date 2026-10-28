"""Manual artifact boundaries reuse board authorization, history and CAS."""
from copy import deepcopy
import json
import unittest
from pydantic import ValidationError
import test_boards as board_fixture
from test_boards import scene, element
from app.board_schemas import Scene


def artifact(engine='B'):
    return {'id':'widget','engine':engine,'schema_version':1,'anchor_id':'anchor',
            'capabilities':['local-state'] if engine=='B' else [],'state':{},
            'payload':{'version':1,'title':'Manual','blocks':[{'type':'calculator','operation':'sum',
                'inputs':[{'label':'Count','min':0,'max':100,'step':1,'value':3}]}]} if engine=='B'
                else {'html':'<h1>Preview</h1>','css':'','javascript':'parent.fetch("/boards")'}}


def drawing(a=None, **patch):
    return scene(element('anchor',width=500,height=350,**patch),artifacts=[a or artifact()])


class ArtifactSchemaTests(unittest.TestCase):
    def test_old_scene_compatibility_and_both_enabled_contracts(self):
        self.assertEqual(Scene.model_validate(scene()).artifacts, [])
        for engine in ['B','C']:
            self.assertEqual(Scene.model_validate(drawing(artifact(engine))).artifacts[0].engine, engine)

    def test_hostile_capabilities_state_and_anchor_references(self):
        bad=[]
        for patch in [{'engine':'A'}, {'engine':'HTML'}, {'capabilities':['network']},
                      {'schema_version':2}, {'schema_version':True}, {'state':{'0':[101]}}, {'state':{'01':[3]}},
                      {'state':{'0':[True]}}, {'state':{'__proto__':[]}}, {'state':{'1':[3]}},
                      {'state':{'0':[float('nan')]}}, {'anchor_id':'other'}, {'token':'secret'}]:
            bad.append(drawing({**artifact(),**patch}))
        for patch in [{'angle':1},{'groupIds':['group']},{'frameId':'frame'},{'width':239},{'height':159}]:
            value=drawing();value['elements'][0].update(patch);bad.append(value)
        value=drawing();value['artifacts']*=2;bad.append(value)
        value=drawing(artifact('C'));value['artifacts'][0]['state']={'token':'secret'};bad.append(value)
        for value in bad:
            with self.subTest(value=str(value)[:120]),self.assertRaises((ValidationError,ValueError)):
                Scene.model_validate(value)

    def test_bounded_widget_count_size_and_deleted_undo_anchors(self):
        Scene.model_validate(drawing(isDeleted=True))
        value=drawing();value['artifacts']*=41
        with self.assertRaises(ValidationError):Scene.model_validate(value)
        value=drawing(artifact('C'));value['artifacts'][0]['payload']['html']='x'*60001
        with self.assertRaises(ValidationError):Scene.model_validate(value)


class ArtifactAPITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = board_fixture.BoardAPITests.asyncSetUp
    asyncTearDown = board_fixture.BoardAPITests.asyncTearDown
    ok = board_fixture.BoardAPITests.ok
    board = board_fixture.BoardAPITests.board
    save = board_fixture.BoardAPITests.save
    async def test_widget_state_reload_history_conflict_archive_and_ownership(self):
        bid=(await self.board())['id']
        first=await self.save(bid,value=drawing())
        value=deepcopy(first['scene']);value['artifacts'][0]['state']={'0':[42]}
        await self.save(bid,1,value)
        self.assertEqual((await self.ok('GET',f'/boards/{bid}/scene'))['scene']['artifacts'][0]['state'],{'0':[42.0]})
        legacy = deepcopy(value)
        legacy.pop('artifacts')
        await self.save(bid,2,legacy,status=422)
        self.assertEqual((await self.ok('GET',f'/boards/{bid}/scene'))['revision'],2)
        await self.save(bid,1,drawing(),status=409)
        restored=await self.ok('POST',f'/boards/{bid}/revisions/1/restore',json={'expected_revision':2})
        self.assertEqual(restored['scene']['artifacts'][0]['state'],{})
        value['artifacts'][0]['capabilities']=['network']
        await self.save(bid,3,value,status=422)
        await self.ok('PATCH',f'/boards/{bid}',json={'status':'archived'})
        await self.save(bid,3,drawing(),status=409)
        original=self.headers
        r=await self.client.post('/auth/signup',json={'email':'intruder@example.com','password':'password123'})
        self.headers={'Authorization':'Bearer '+r.json()['token']}
        await self.ok('GET',f'/boards/{bid}/scene',404)
        await self.save(bid,3,drawing(),status=404)
        await self.ok('GET',f'/boards/{bid}/revisions/1',404)
        self.headers=original


class InteractiveFormTests(unittest.TestCase):
    def test_form_controls_layout_and_state_contract(self):
        from app.canvas_artifacts import StructuredArtifact
        from app.quickui import Specification, fallback
        spec={'version':1,'title':'Circuit','blocks':[{'type':'form','fields':[
            {'label':'Name','kind':'text','value':''},
            {'label':'Gate','kind':'select','options':['NAND','OR'],'value':'NAND'},
            {'label':'Active','kind':'switch','value':False}]}]}
        item={'id':'form','anchor_id':'anchor','engine':'B','schema_version':1,'capabilities':['local-state'],'payload':spec,'state':{'0':{'values':['Chip','OR',True],'submitted':True}},'layout':{'auto_width':False,'auto_height':True}}
        self.assertEqual(StructuredArtifact.model_validate(item).state['0']['values'],['Chip','OR',True])
        self.assertIn('Name',fallback(Specification.model_validate(spec).model_dump()))
        for values in [['Chip','INVALID',True],['x'*4001,'OR',True],['Chip','OR','yes']]:
            with self.assertRaises(ValueError):StructuredArtifact.model_validate({**item,'state':{'0':{'values':values}}})
        with self.assertRaises(ValueError):StructuredArtifact.model_validate({**item,'layout':{'auto_height':'false'}})
