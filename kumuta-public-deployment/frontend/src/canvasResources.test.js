import assert from 'node:assert/strict';
import {resourceReference,validResourceFrames} from './canvasResources.js';
const reference=resourceReference({kind:'document',source_id:1,fingerprint:'a'.repeat(64),format:'pdf'});
assert.equal(reference.page,1);
const frame={id:'r',anchor_id:'anchor',schema_version:1,reference},anchor={id:'anchor',type:'rectangle',angle:0,width:460,height:420,groupIds:[]};
assert(validResourceFrames([frame],[anchor]));
assert(!validResourceFrames([frame,frame],[anchor]));
assert(!validResourceFrames([frame],[{...anchor,angle:1}]));
assert(!validResourceFrames([frame],[anchor],[{anchor_id:'anchor'}]));
assert(!validResourceFrames([{...frame,reference:{...reference,source_id:-1}}],[anchor]));
assert(validResourceFrames([frame],[{...anchor,isDeleted:true}])); // Retain reference for native Undo.
console.log('Resource anchors reject forged contracts and preserve tombstoned native history.');
