import test from 'node:test';
import assert from 'node:assert/strict';
import {chartBlock,defaultSpec,moveWidget,parseSpecDraft} from './dataAnalysis.js';
const result=()=>({columns:['category','Revenue'],column_types:{category:'string',Revenue:'decimal'},rows:[['A','10.50'],['B','20']],spec:defaultSpec()});
test('chart conversion never fabricates missing/unsafe values as zero',()=>{assert.deepEqual(chartBlock(result()).series[0].values,[10.5,20]);for(const value of [null,'not numeric','999999999999999999']){const r=result();r.rows[0][1]=value;assert.equal(chartBlock(r),null);}const r=result();r.rows=Array.from({length:101},()=>['A','1']);assert.equal(chartBlock(r),null);});
test('area shares chart data and reorder preserves declarative identity',()=>{const r=result();r.spec.chart='area';assert.equal(chartBlock(r).kind,'area');const widgets=[{key:'one'},{key:'two'}];assert.deepEqual(moveWidget(widgets,1,-1).map(w=>w.key),['two','one']);assert.deepEqual(widgets.map(w=>w.key),['one','two']);});
test('advanced draft rejects types that could crash React controls',()=>{assert.equal(parseSpecDraft('{"operation":"rows","metrics":[]}').operation,'rows');for(const raw of ['null','{"metrics":[null]}','{"filters":[{"column":{},"op":"eq"}]}','{"sort":null}','{"limit":10000}'])assert.throws(()=>parseSpecDraft(raw));});

test('chart switching uses result shape and rejects unsafe values',async()=>{
 const {supportedCharts}=await import('./dataAnalysis.js');
 const r=result();assert.ok(supportedCharts(r).includes('pie'));assert.ok(!supportedCharts(r).includes('scatter'));
 r.columns.push('Quantity');r.column_types.Quantity='integer';r.rows.forEach(row=>row.push(2));assert.ok(supportedCharts(r).includes('scatter'));assert.ok(!supportedCharts(r).includes('pie'));
 r.rows[0][1]=null;assert.deepEqual(supportedCharts(r),['table']);
 assert.equal(parseSpecDraft('{"chart":"scatter"}').chart,'scatter');
});
