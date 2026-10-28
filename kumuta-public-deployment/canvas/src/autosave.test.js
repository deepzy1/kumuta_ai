import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Autosave } from './autosave.js';
const scene=n=>({elements:[{id:'a',x:n}]});
const tick=()=>new Promise(r=>setTimeout(r,5));
test('serialized requests use latest revision and coalesce edits during in-flight save',async()=>{
  let release,active=0,max=0;const calls=[];
  const q=new Autosave({revision:4,scene:scene(0),delay:100000,save:async(s,r)=>{active++;max=Math.max(max,active);calls.push([s,r]);if(calls.length===1)await new Promise(r=>release=r);active--;return {revision:r+1};}});
  q.change(scene(1));const flushing=q.flush();await tick();q.change(scene(2));q.change(scene(3));const parallel=q.flush();release();await Promise.all([flushing,parallel]);
  assert.equal(max,1);assert.deepEqual(calls.map(([s,r])=>[s.elements[0].x,r]),[[1,4],[3,5]]);assert.equal(q.dirty,false);assert.equal(q.revision,6);q.dispose();
});
test('debounce skips unchanged scenes and collapses rapid edits',async()=>{
  const calls=[];const q=new Autosave({revision:0,scene:scene(0),delay:8,save:async(s,r)=>{calls.push(s);return {revision:r+1};}});
  q.change(scene(0));q.change(scene(1));q.change(scene(2));await new Promise(r=>setTimeout(r,40));assert.equal(calls.length,1);assert.deepEqual(calls[0],scene(2));q.dispose();
});
test('409 preserves local edits and stops retries and subsequent changes',async()=>{
  let calls=0;const states=[];const error=Object.assign(new Error('conflict'),{status:409});
  const q=new Autosave({revision:1,scene:scene(0),delay:100000,onState:s=>states.push(s),save:async()=>{calls++;throw error;}});
  q.change(scene(1));await assert.rejects(q.flush(),error);q.change(scene(2));await assert.rejects(q.retry(),error);assert.equal(calls,1);assert.equal(q.revision,1);assert.deepEqual(q.latest,scene(2));assert.equal(states.at(-1).status,'conflict');q.dispose();
});
for(const status of [413,422,0,401])test(`failed ${status} save retains scene and revision; explicit retry only`,async()=>{
  let calls=0;const q=new Autosave({revision:2,scene:scene(0),delay:100000,save:async(s,r)=>{if(++calls===1)throw Object.assign(new Error('failure'),{status});return {revision:r+1};}});
  q.change(scene(1));await assert.rejects(q.flush());assert.equal(q.dirty,true);assert.equal(q.revision,2);await tick();assert.equal(calls,1);await q.retry();assert.equal(q.dirty,false);assert.equal(q.revision,3);q.dispose();
});
test('disposal cancels debounce and prevents post-unmount callbacks',async()=>{
  let calls=0;const q=new Autosave({revision:0,scene:scene(0),delay:5,save:async()=>{calls++;return {revision:1};}});q.change(scene(1));q.dispose();await new Promise(r=>setTimeout(r,20));assert.equal(calls,0);
});

test('unchanged native onChange callbacks do not trigger a React update loop',()=>{let reports=0;const q=new Autosave({revision:1,scene:scene(0),save:async()=>{},onState:()=>reports++});for(let i=0;i<100;i++)q.change(scene(0));assert.equal(reports,1);q.dispose();});

test('removing an invalid edit restores saved feedback even when scene equals baseline',()=>{const states=[];const q=new Autosave({revision:1,scene:scene(0),save:async()=>{},onState:s=>states.push(s.status)});q.change(scene(0));q.error=new Error('invalid');q.report('invalid',q.error);q.error=null;q.change(scene(0));assert.deepEqual(states,['saved','invalid','saved']);q.dispose();});
