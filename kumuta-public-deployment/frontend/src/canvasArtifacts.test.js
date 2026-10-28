import test from 'node:test';
import assert from 'node:assert/strict';
import {manualExample,diagramSkeleton,validateManual,validArtifact,validInteraction,validAnchors} from './canvasArtifacts.js';
const artifact=kind=>({id:'a',anchor_id:'anchor',schema_version:1,state:{},...manualExample(kind)});
test('all manual engine examples validate without providers',()=>{
 for(const k of ['flowchart','mindmap','architecture','chart','table','cards','calculator','checklist','timeline','progress','custom'])assert.equal(validateManual(manualExample(k)).engine,manualExample(k).engine);
});
test('unknown routing, native references, invalid controls and capabilities fail closed',()=>{
 assert.throws(()=>validateManual({engine:'__proto__',payload:{},capabilities:[]}));
 const n=manualExample('flowchart');n.payload.edges[0].to='missing';assert.throws(()=>validateManual(n));
 for(const k of ['chart','calculator','custom']){const a=artifact(k);a.capabilities=['network'];assert.equal(validArtifact(a),false);}
 const a=artifact('calculator');a.payload.blocks[0].inputs[0].max=0;assert.equal(validArtifact(a),false);
 const b=artifact('chart');b.payload.title={bad:'object'};assert.equal(validArtifact(b),false);
 const c=artifact('chart');c.payload.blocks[0].sources={bad:true};assert.equal(validArtifact(c),false);
});
test('controlled state rejects cross-component keys, out-of-range values and executable fields',()=>{
 const p=manualExample('calculator').payload;assert.equal(validInteraction(p,{'0':[5,42]}),true);
 for(const s of [{'0':[0,42]},{'0':[5,Infinity]},{'01':[5,42]},{'1':[5,42]},JSON.parse('{"__proto__":[5,42]}')])assert.equal(validInteraction(p,s),false);
 const a=artifact('checklist');a.state={'0':[false,true]};assert.equal(validArtifact(a),true);a.state={'0':['false',true]};assert.equal(validArtifact(a),false);
 const c=artifact('custom');c.state={token:'secret'};assert.equal(validArtifact(c),false);
});
test('anchors reject missing, grouped, rotated, duplicate and unsupported geometry',()=>{
 const a=artifact('chart'),e={id:'anchor',type:'rectangle',x:0,y:0,angle:0,width:500,height:350};
 assert.equal(validAnchors([a],[e]),true);
 for(const patch of [{angle:1},{width:10},{groupIds:['g']},{frameId:'f'}])assert.equal(validAnchors([a],[{...e,...patch}]),false);
 assert.equal(validAnchors([a,a],[e]),false);assert.equal(validAnchors([a],[]),false);
});
test('result table filters persist as bounded text and reject executable state',()=>{
 const spec=manualExample('table').payload;
 assert.equal(validInteraction(spec,{'0':'In progress'}),true);
 for(const value of ['x'.repeat(121),{query:'x',sql:'select *'},['x']])assert.equal(validInteraction(spec,{'0':value}),false);
});

test('native arrows connect declared nodes at their boundaries rather than the origin',()=>{
 const data=manualExample('flowchart').payload;
 const out=diagramSkeleton(data,'fixture',400,200), arrows=out.filter(e=>e.type==='arrow');
 assert.equal(arrows.length,2);assert.equal(arrows[0].start.id,'fixture-node-0');assert.equal(arrows[0].end.id,'fixture-node-1');
 assert(arrows.every(e=>e.x>500&&e.y>200&&e.points[1][0]>0));
});

test('long user IDs and edge-like node names cannot collide with native IDs',()=>{
 const p=manualExample('flowchart').payload;p.nodes[0].id='x'.repeat(128);p.edges[0].from=p.nodes[0].id;p.nodes[2].id='edge-0';p.edges[1].to='edge-0';validateManual({engine:'A',payload:p,capabilities:[]});
 const out=diagramSkeleton(p,'a'.repeat(36));assert.equal(new Set(out.map(e=>e.id)).size,out.length);assert(out.every(e=>e.id.length<=128));
});

test('forms preserve bounded independent field state and reject undeclared options',()=>{
  const spec={version:1,title:'Circuit',blocks:[{type:'form',fields:[{label:'Name',kind:'text',value:''},{label:'Gate',kind:'select',options:['NAND','OR'],value:'NAND'},{label:'Active',kind:'switch',value:false}]}]};
  const widget={id:'first',anchor_id:'anchor',engine:'B',schema_version:1,capabilities:['local-state'],payload:spec,state:{'0':{values:['Chip','OR',true],submitted:true}},layout:{auto_width:false,auto_height:true}};
  assert(validArtifact(widget));
  assert(!validArtifact({...widget,state:{'0':{values:['Chip','INVALID',true]}}}));
  assert(!validArtifact({...widget,state:{'0':{values:['x'.repeat(4001),'OR',true]}}}));
  assert(!validArtifact({...widget,layout:{auto_width:'false'}}));
});
