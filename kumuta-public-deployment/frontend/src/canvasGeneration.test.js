import test from 'node:test';
import assert from 'node:assert/strict';
import { generationElements } from './generationPlacement.js';
import { generationRequest, pendingJob, generationLabel } from './canvasGeneration.js';
import { manualExample } from './canvasArtifacts.js';

test('reusing an explicit request preserves idempotency and regeneration targets',()=>{
  const a=generationRequest('diagram','A','artifact','stable_key');
  assert.deepEqual(a,generationRequest('diagram','A','artifact','stable_key'));
  assert.equal(a.artifact_id,'artifact');assert.equal(a.request_key,'stable_key');
  assert.equal(pendingJob({status:'generating'}),true);
  for(const status of ['completed','failed','cancelled','timed_out'])assert.equal(pendingJob({status}),false);
  assert.equal(generationLabel('validating'),'Validating specification');
});

test('native bound text and arrow identities become stable within an immutable version',()=>{
  const namespace='a'.repeat(32)+'_v1';
  const convert=()=>[
    {id:'shape',type:'rectangle',boundElements:[{id:'random-label',type:'text'},{id:'random-arrow',type:'arrow'}]},
    {id:'random-label',type:'text',containerId:'shape'},
    {id:'random-arrow',type:'arrow',startBinding:{elementId:'shape'},endBinding:{elementId:'other'}},
    {id:'other',type:'rectangle'},
  ];
  const result=generationElements(manualExample('architecture'),namespace,0,0,convert);
  assert.equal(result[1].containerId,result[0].id);
  assert.equal(result[0].boundElements[0].id,result[1].id);
  assert.equal(result[2].startBinding.elementId,result[0].id);
  assert.equal(result[2].endBinding.elementId,result[3].id);
  assert.ok(result.every(e=>e.id.startsWith(namespace+'-')));
  assert.deepEqual(result,generationElements(manualExample('architecture'),namespace,0,0,convert));
});

test('Custom execution and unvalidated generated specifications never enter placement conversion',()=>{
  assert.throws(()=>generationElements(manualExample('custom'),'a'.repeat(32)+'_v1',0,0,()=>[]),/disabled/);
  assert.throws(()=>generationElements({engine:'B',capabilities:[],payload:{html:'<script>'}},'a'.repeat(32)+'_v1',0,0,()=>[]));
  assert.throws(()=>generationElements(manualExample('chart'),'bad',0,0,()=>[]),/namespace/);
});
