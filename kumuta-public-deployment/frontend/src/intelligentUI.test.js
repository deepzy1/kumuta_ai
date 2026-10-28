import test from 'node:test';
import assert from 'node:assert/strict';
import {formulaValue,validFormulas,tableState,tableRows,scopedRows,aggregates,validTableState,csvData,calculatorResults,seriesColor} from './intelligentUI.js';
import {validSpec} from './quickui.js';
import {validInteraction,validateManual} from './canvasArtifacts.js';
import {crc32,pdfBytes,zipBytes,filename} from './componentExport.js';
const table={type:'table',columns:['Name','Amount','Status'],rows:[['A',2,'Won'],['B',10,'Open'],['C',5,'Won']]};
test('filtered, selected and visible rows remain distinct across sort and pagination',()=>{
 const state={...tableState(''),filters:{2:'won'},selected:[0,1,2],sort:{column:1,direction:'desc'}};
 assert.deepEqual(tableRows(table,state).map(r=>r.id),[2,0]);assert.deepEqual(scopedRows(table,state,'selected').map(r=>r.id),[2,0]);
 assert.equal(aggregates(table,scopedRows(table,state,'selected'))[0].sum,7);
 const large={...table,rows:Array.from({length:65},(_,i)=>['N'+i,i,'Open'])};
 assert.equal(scopedRows(large,{...state,filters:{},page:1,pageSize:25},'visible').length,25);
 assert.deepEqual(scopedRows(large,{...state,filters:{},page:100,pageSize:25},'visible').map(r=>r.id),Array.from({length:15},(_,i)=>14-i));
 assert(validTableState(table,state));assert(validInteraction({blocks:[table]},{0:state}));assert(validInteraction({blocks:[table]},{0:'old filter'}));
 for(const bad of [{...state,selected:[3]},{...state,hidden:[0,1,2]},{...state,filters:{99:'x'}},{...state,pageSize:100000},{...state,sort:{column:1,direction:'bad'}}])assert(!validTableState(table,bad));
});
test('formula grammar supports forecasts and dependencies, rejects code and forward references',()=>{
 assert(Math.abs(formulaValue('x1*(1+x2/100)^6',[100,20])-298.5984)<1e-9);
 assert(Math.abs(formulaValue('(r1-x1)/r1*100',[100],[120])-100/6)<1e-12);
 assert.equal(formulaValue('-2^2',[]),-4);assert.equal(formulaValue('2^-2',[]),.25);
 assert(validFormulas(['x1/0','r1*x1'],1));
 for(const f of ['x1.constructor','alert(1)','x1=3','Math.random()','r1+1','x2+1','1;2','2**3','2//1','0x1','01','00','9'.repeat(250)])assert(!validFormulas([f],1),f);
 assert.throws(()=>formulaValue('x1/0',[1]),/divide/);assert.throws(()=>formulaValue('2^9999',[]),/range/);
 const block={type:'calculator',operation:'formula',inputs:[{label:'Revenue',min:0,max:10000,value:100,step:1}],formulas:[{label:'Double',expression:'x1*2'},{label:'Margin',expression:'(r1-x1)/r1*100'}]};
 validateManual({engine:'B',capabilities:['local-state'],payload:{version:1,blocks:[block]}});
 assert.equal(calculatorResults(block,{values:[250],expressions:['x1*2','(r1-x1)/r1*100']})[1].value,50);
 assert(validInteraction({blocks:[block]},{0:{values:[250],expressions:['x1*2','r1+1']}}));
 assert(!validInteraction({blocks:[block]},{0:{values:[250],expressions:['r1+2','x1']}}));
 assert(!validSpec({version:1,blocks:[{...block,formulas:[{label:'Bad',expression:'fetch(x1)'}]}]}));
});
test('chart contracts, stable color identity and CSV formula injection protection',()=>{
 for(const kind of ['bar','line','area','stacked','scatter','pie','donut'])assert(validSpec({version:1,blocks:[{type:'chart',kind,labels:['1','2'],series:[{name:'Series',values:[2,3]}]}]}));
 assert(!validSpec({version:1,blocks:[{type:'chart',kind:'pie',labels:['A'],series:[{name:'Series',values:[-2]}]}]}));
 assert.equal(seriesColor('Revenue'),seriesColor('Revenue'));
 assert.match(csvData(['A'],[['=HYPERLINK("bad")']]),/'=HYPERLINK/);
});
test('export encoders create ordered ZIP entries, valid byte offsets and a PDF page tree',()=>{
 assert.equal(crc32(new TextEncoder().encode('123456789')),0xcbf43926);
 const zip=zipBytes([{name:'01-A.txt',data:new TextEncoder().encode('Alpha')},{name:'02-B.txt',data:new TextEncoder().encode('Beta')}]);
 const view=new DataView(zip.buffer);assert.equal(view.getUint32(0,true),0x04034b50);assert.equal(view.getUint32(zip.length-22,true),0x06054b50);assert.equal(view.getUint16(zip.length-12,true),2);
 const pdf=pdfBytes(Array.from({length:4},()=>({data:new Uint8Array([255,216,255,217]),width:10,height:10,pageWidth:842,pageHeight:595,drawWidth:100,drawHeight:100,x:24,y:24,pageNumbers:true})));
 const text=new TextDecoder().decode(pdf);assert.match(text,/\/Count 4/);assert.equal((text.match(/\/Type \/Page /g)||[]).length,4);assert.match(text,/Page 4 of 4/);
 const xref=Number(text.match(/startxref\n(\d+)/)[1]);assert.equal(text.slice(xref,xref+4),'xref');
 assert.equal(filename('../../report',3),'04-report');
});
