import test from 'node:test';
import assert from 'node:assert/strict';
import {intelligenceSelection,intelligenceReferences,applicableActions} from './canvasIntelligence.js';
const a={kind:'document',source_id:1,fingerprint:'a'.repeat(64),status:'ready',filename:'A.pdf',format:'pdf'};
const b={kind:'dataset',source_id:2,fingerprint:'b'.repeat(64),status:'ready',filename:'B.csv'};
test('source scope never broadens a selected subset and selection remains native',()=>{
  const value={scope:'selected',operation:'ask',keys:['document:1']};
  const request=intelligenceSelection(value,[a,b],null,4,'Find evidence');
  assert.deepEqual(request.resources.map(r=>r.source_id),[1]);assert.equal(request.expected_revision,4);
  assert.equal(request.intelligence.query,'Find evidence');
  const selection={request:{expected_revision:4,element_ids:['native']}};
  assert.equal(intelligenceSelection({...value,scope:'selection'},[a,b],selection,4,'test'),selection.request);
});
test('board scope includes ready documents/datasets and exact worksheet choices',()=>{
  const refs=intelligenceReferences({scope:'board',sheets:{'dataset:2':'PrivateChoice'}},[a,b,{...a,source_id:3,status:'processing'},{kind:'image',source_id:4,status:'ready'}]);
  assert.equal(refs.length,2);assert.equal(refs[1].sheet,'PrivateChoice');
});
test('actions reflect source types and explicit multi-source context',()=>{
  assert.ok(applicableActions([a,b]).includes('compare'));assert.ok(applicableActions([b]).includes('analyze'));
  assert.ok(!applicableActions([a]).includes('analyze'));assert.ok(!applicableActions([b]).includes('search'));
});
test('multiple worksheets require explicit selections within the chosen workbook',()=>{
 const refs=intelligenceReferences({scope:'selected',keys:['dataset:2'],sheets:{'dataset:2':['Q1','Q2']}},[a,b]);
 assert.deepEqual(refs.map(r=>r.sheet),['Q1','Q2']);assert.ok(refs.every(r=>r.source_id===2));
 const narrowed=intelligenceReferences({scope:'resource',keys:['dataset:2'],sheets:{'dataset:2':['Q1','Q2']}},[b]);
 assert.deepEqual(narrowed.map(r=>r.sheet),['Q1']);
});

test('automatic dataset actions follow UI/chart intent and remain visible before sending',async()=>{
 const {resolveSourceAction,sourceSummary}=await import('./canvasIntelligence.js');
 const value={scope:'selected',operation:'ask',keys:['dataset:2']},data={...b,sheets:[{name:'Sales'}]};
 assert.equal(resolveSourceAction(value,[data],null,'ui','Explain this spreadsheet').operation,'visualize');
 for(const prompt of ['create a bar graph','Create a chart','Show a revenue dashboard'])assert.equal(resolveSourceAction(value,[data],null,'auto',prompt).operation,'visualize');
 assert.equal(resolveSourceAction(value,[data],null,'auto','Explain what a bar graph means').operation,'ask');
 assert.equal(resolveSourceAction(value,[data],null,'chat','Explain this spreadsheet').operation,'ask');
 assert.equal(resolveSourceAction(value,[data],null,'chat','Calculate total revenue').operation,'analyze');
 assert.equal(sourceSummary(value,[data]),'B.csv · Sales');
 assert.deepEqual(intelligenceReferences(value,[a,data]),intelligenceReferences(resolveSourceAction(value,[a,data],null,'ui','Create dashboard'),[a,data]));
});
test('manual actions and native/row selections are preserved and Auto re-evaluates each draft',async()=>{
 const {resolveSourceAction,sourceSummary}=await import('./canvasIntelligence.js');
 const manual={scope:'selected',operation:'ask',automatic:false,keys:['dataset:2']};
 assert.equal(resolveSourceAction(manual,[b],null,'ui','Create a graph'),manual);
 const selected={...manual,scope:'selection',automatic:true};assert.equal(resolveSourceAction(selected,[b],{request:{resources:[{kind:'dataset',source_id:2,row_start:2,row_end:3}]}},'ui','Create chart'),selected);
 const visual={...manual,operation:'visualize',automatic:true};assert.equal(resolveSourceAction(visual,[b],null,'auto','Explain this file').operation,'ask');
 assert.equal(resolveSourceAction({...visual,keys:['document:1']},[a,b],null,'ui','Create widget').operation,'ask');
 assert.equal(sourceSummary(selected,[b],{context:{element_ids:[],resources:[{label:'Sales.csv · selected row 2'}]}}),'Sales.csv · selected row 2');
});
