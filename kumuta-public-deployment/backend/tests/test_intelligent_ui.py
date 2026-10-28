"""Extended contracts and authoritative row scopes over the existing lifecycle."""
import copy
import json
import unittest
from pydantic import ValidationError
from app import quickui, canvas_openui
from app.canvas_artifacts import validate_state
from app.intelligent_ui import validate_formula, evaluate_formula, project_table
from test_boards import element, scene
import test_canvas_generation as gen
import test_shared_ai as shared_tests

TABLE={'type':'table','columns':['Name','Revenue','Status'],'rows':[['A',2,'Won'],['B',10,'Open'],['C',5,'Won']]}
STATE={'query':'','filters':{'2':'won'},'selected':[0,1,2],'sort':{'column':1,'direction':'desc'},'page':0,'pageSize':25,'hidden':[],'widths':{}}
FORMULA={'type':'calculator','operation':'formula','inputs':[{'label':'Revenue','min':0,'max':10000,'value':100,'step':1}], 'formulas':[{'label':'Double','expression':'x1*2'},{'label':'Margin','expression':'(r1-x1)/r1*100'}]}

class ContractTests(unittest.TestCase):
    def test_registry_legacy_and_extended_components(self):
        for block in [TABLE,FORMULA,*[{'type':'chart','kind':kind,'labels':['1','2'],'series':[{'name':'Metric','values':[2,3]}]} for kind in ('bar','line','area','stacked','scatter','pie','donut')]]:
            spec=quickui.Specification.model_validate({'version':1,'blocks':[block]})
            validate_state(spec,{})
        compiled=canvas_openui.parse_program('root=Stack("Formula",[Calculator("", "formula", [{"label":"Value","value":2,"min":0,"max":10,"step":1}], "USD", [{"label":"Double","expression":"x1*2"}])]);')
        self.assertEqual(compiled['blocks'][0]['formulas'][0]['expression'],'x1*2')
        from app.canvas_generation_schemas import validate_generated, route_mode
        for prompt in ['Calculate projected revenue for six months with 20% growth and show profit margin','Forecast loan repayments','Show the customer records in a table']:
            self.assertEqual(route_mode(prompt),'B')
        for prompt in ['What is compound interest?','Explain revenue growth','Calculate 2+2','Show me how a table works']:
            self.assertEqual(route_mode(prompt),'T')
        self.assertEqual(validate_generated('B','root=Stack("Text",[Text("Note","Explain supplied evidence")]);','openui-lang-v1')['payload']['blocks'][0]['type'],'markdown')
        self.assertAlmostEqual(evaluate_formula('x1*(1+x2/100)^6',[100,20],[]),298.5984)
        self.assertEqual(evaluate_formula('r1-x1',[100],[120]),20)
        with self.assertRaises(ValueError):evaluate_formula('x1/0',[100],[])
        self.assertEqual(canvas_openui.parse_program('root=Stack("Legacy",[Table("",["A"],[[1]])]);')['blocks'][0]['rows'],[[1]])

    def test_formula_syntax_bounds_no_execution_or_forward_references(self):
        for expression in ['x1*(1+x2/100)^6','x1/0','-2^2','2^-2','(r1-x1)/r1*100']:
            validate_formula(expression,2,1)
        for expression in ['__import__("os")','x1.real','r2+1','x3+1','1;2','2**3','2//1','1e999','0x1','01','00','9'*250]:
            with self.assertRaises(ValueError,msg=expression):validate_formula(expression,2,1)
        with self.assertRaises(ValueError):quickui.Calculator.model_validate({**FORMULA,'formulas':[{'label':'Forward','expression':'r1+1'}]})

    def test_table_state_rejects_forged_indexes_and_invalid_column_states(self):
        spec=quickui.Specification.model_validate({'blocks':[TABLE]})
        validate_state(spec,{'0':STATE});validate_state(spec,{'0':'legacy'})
        for patch in [{'selected':[3]},{'selected':[True]},{'hidden':[0,1,2]},{'filters':{'01':'a'}},{'sort':{'column':0,'direction':'bad'}},{'pageSize':999999},{'widths':{'0':601}}]:
            with self.assertRaises(ValueError):validate_state(spec,{'0':{**STATE,**patch}})

    def test_selected_filtered_visible_scope_and_no_mutation(self):
        before=copy.deepcopy(TABLE)
        self.assertEqual(project_table(TABLE,STATE,'selected')['row_ids'],[2,0])
        self.assertEqual(project_table(TABLE,{**STATE,'selected':[1]},'selected')['rows'],[])
        self.assertEqual(project_table(TABLE,{**STATE,'selected':[1]},'filtered')['rows'],[['C',5,'Won'],['A',2,'Won']])
        self.assertEqual(TABLE,before)

    def test_formula_interaction_validation(self):
        spec=quickui.Specification.model_validate({'blocks':[FORMULA]})
        validate_state(spec,{'0':[250]});validate_state(spec,{'0':{'values':[250],'expressions':['x1*2','r1+1']}})
        for value in [{'values':[250],'expressions':['r1+1','r2']},{'values':[10001],'expressions':['x1','r1']},{'values':[250],'expressions':['x1']}, {'values':[250],'expressions':['x1','r1'],'extra':1}]:
            with self.assertRaises(ValueError):validate_state(spec,{'0':value})

    def test_chart_and_table_limits(self):
        quickui.Table.model_validate({**TABLE,'rows':TABLE['rows']*333})
        with self.assertRaises(ValidationError):quickui.Table.model_validate({**TABLE,'rows':TABLE['rows']*334})
        with self.assertRaises(ValidationError):quickui.Chart.model_validate({'type':'chart','kind':'pie','labels':['A'],'series':[{'name':'Bad','values':[-2]}]})
        with self.assertRaises(ValidationError):quickui.Chart.model_validate({'type':'chart','kind':'scatter','labels':['Unknown'],'series':[{'name':'Bad','values':[2]}]})


class IntelligentSelectionTests(unittest.IsolatedAsyncioTestCase):
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

    async def table_scene(self):
        value=scene(element('table-anchor',width=720,height=600),element('unrelated',x=1200))
        value['artifacts']=[{'id':'manual-table','anchor_id':'table-anchor','engine':'B','schema_version':1,'capabilities':['local-state'],'payload':{'version':1,'title':'Actual records','blocks':[TABLE]},'state':{'0':STATE}}]
        await self.save(self.bid,value=value)

    async def test_row_resolution_uses_saved_filtered_selection_and_rejects_forged_scopes(self):
        await self.table_scene()
        request={'expected_revision':1,'element_ids':['table-anchor'],'action':'explain'}
        result=await self.ok('POST',f'/boards/{self.bid}/selection/resolve',json=request)
        table=result['widgets'][0]
        self.assertEqual(table['payload']['blocks'][0]['rows'],[['C',5,'Won'],['A',2,'Won']])
        self.assertEqual(table['table_context'][0]['scope'],'selected');self.assertEqual(table['state'],{})
        self.assertNotIn('unrelated',json.dumps(result))
        for scope in ('filtered','visible','selected'):
            result=await self.ok('POST',f'/boards/{self.bid}/selection/resolve',json={**request,'table_scopes':[{'anchor_id':'table-anchor','block_index':0,'scope':scope}]})
            self.assertEqual(len(result['widgets'][0]['payload']['blocks'][0]['rows']),2)
        await self.ok('POST',f'/boards/{self.bid}/selection/resolve',422,json={**request,'table_scopes':[{'anchor_id':'unrelated','block_index':0,'scope':'filtered'}]})
        saved=await self.ok('GET',f'/boards/{self.bid}/scene')
        self.assertEqual(len(saved['scene']['artifacts'][0]['payload']['blocks'][0]['rows']),3)
        self.assertEqual(self.calls,0)

    async def test_derived_proposal_inserts_preserves_original_and_rejects_replacement(self):
        await self.table_scene();self.response=gen.WIDGET
        job=await self.create(engine='B',mode='ui',selection={'expected_revision':1,'element_ids':['table-anchor'],'action':'derive'})
        done=await self.finish();self.assertEqual(done['status'],'completed',done)
        await self.place(job['artifact_id'],revision=1,engine='B',operation='selection',status=422)
        result=await self.place(job['artifact_id'],revision=1,engine='B',operation='insert')
        self.assertEqual(len(result['scene']['artifacts']),2)
        self.assertFalse(next(e for e in result['scene']['elements'] if e['id']=='table-anchor')['isDeleted'])
        self.assertEqual(result['scene']['artifacts'][0]['payload']['blocks'][0]['rows'],TABLE['rows'])


class AdvancedChatTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=gen.GenerationAPITests.asyncSetUp
    asyncTearDown=gen.GenerationAPITests.asyncTearDown
    ok=gen.GenerationAPITests.ok
    board=gen.GenerationAPITests.board
    setup_chat=shared_tests.SharedChatTests.setup_chat
    send=shared_tests.SharedChatTests.send

    async def test_advanced_shared_chat_state_persists_and_rejects_forged_rows_formulas(self):
        await self.setup_chat()
        program='root=Stack("Advanced shared controls",[Table("Records",'+json.dumps(TABLE['columns'])+','+json.dumps(TABLE['rows'])+'),Calculator("Scenario","formula",'+json.dumps(FORMULA['inputs'])+',"USD",'+json.dumps(FORMULA['formulas'])+')]);'
        self.response='Before\n```openui\n'+program+'\n```\nAfter'
        message=await self.send()
        self.assertEqual(message['quickui']['blocks'][1]['operation'],'formula')
        path=f'/conversations/{self.cid}/messages/{message["id"]}/quickui-state'
        state={'0':STATE,'1':{'values':[250],'expressions':['x1*2','r1-x1']}}
        await self.ok('PUT',path,json={'revision':0,'state':state})
        loaded=(await self.ok('GET',f'/conversations/{self.cid}'))['messages'][-1]
        self.assertEqual(loaded['quickui_state'],state)
        for wrong in [{'0':{**STATE,'selected':[999]}},{'1':{'values':[250],'expressions':['r1','x1']}}]:
            await self.ok('PUT',path,422,json={'revision':1,'state':wrong})
        self.assertEqual(self.calls,1)
