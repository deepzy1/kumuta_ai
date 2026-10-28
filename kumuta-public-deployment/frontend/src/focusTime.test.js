import test from 'node:test';
import assert from 'node:assert/strict';
import { timerSnapshot, timerSeconds, durationText } from './focusTime.js';
test('timestamp display survives inactive intervals and never becomes negative',()=>{
 const snapshot=timerSnapshot({status:'running',elapsed_seconds:30,planned_seconds:1500},1000);
 assert.equal(timerSeconds(snapshot,61000),1410);
 assert.equal(timerSeconds(snapshot,2000000),0);
 assert.equal(timerSeconds(timerSnapshot({status:'paused',elapsed_seconds:30,planned_seconds:60},0),100000),30);
 assert.equal(timerSeconds(timerSnapshot({status:'running',elapsed_seconds:30,planned_seconds:null},0),60000),90);
 assert.equal(durationText(3661),'1:01:01');assert.equal(durationText(-1),'00:00');
});
