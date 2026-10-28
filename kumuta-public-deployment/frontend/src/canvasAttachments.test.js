import test from 'node:test';
import assert from 'node:assert/strict';
import {attachmentKind,validateCanvasFiles,withoutAttachmentSource,CANVAS_ACCEPT} from './canvasAttachments.js';
const file=(name,type='',size=100)=>({name,type,size});
test('picker and shared draft validator accept every supported format, including empty browser MIME',()=>{
 for(const ext of ['pdf','docx','txt','md','csv','xlsx','png','jpg','jpeg']){
  assert(CANVAS_ACCEPT.includes('.'+ext));assert.equal(validateCanvasFiles([],[file('sample.'+ext)]),'');
 }
 assert.equal(attachmentKind(file('BOOK.XLSX')),'dataset');assert.equal(attachmentKind(file('paste.png')),'image');
 assert.equal(validateCanvasFiles([],[file('sheet.csv','text/plain')]),'');
});
test('executables, macros, archives, MIME mismatch and size/count/aggregate limits fail before upload',()=>{
 for(const ext of ['exe','js','zip','xlsm','xls','svg','gif'])assert.match(validateCanvasFiles([],[file('unsafe.'+ext)]),/Choose/);
 assert.match(validateCanvasFiles([],[file('fake.pdf','image/png')]),/Choose/);
 assert.match(validateCanvasFiles([],[file('empty.txt','',0)]),/nonempty/);
 assert.match(validateCanvasFiles([],[file('big.xlsx','',4*1024*1024+1)]),/4 MiB/);
 assert.match(validateCanvasFiles([],[file('big.pdf','',8*1024*1024+1)]),/8 MiB/);
 assert.match(validateCanvasFiles(Array(5).fill(file('a.txt')),[file('b.txt')]),/5 files/);
 assert.match(validateCanvasFiles(Array(2).fill(file('a.pdf','',8*1024*1024)),[file('b.pdf','',8*1024*1024)]),/20 MiB/);
});
test('removal narrows selected scope without modifying other sources',()=>{
 const value={scope:'selected',keys:['document:1','dataset:2'],confirmFull:true};
 assert.deepEqual(withoutAttachmentSource(value,{kind:'document',source_id:1}),{scope:'selected',keys:['dataset:2'],confirmFull:false});
 assert.equal(withoutAttachmentSource(value,null),value);
});

test('WebP stays blocked under the owner-retained MIT/Apache policy',()=>{assert.match(validateCanvasFiles([],[file('valid.webp','image/webp')]),/WebP decoding is unavailable/);});

test('removing an attachment from Board resources explicitly narrows the scope',()=>{
 const resource={kind:'document',source_id:1,status:'ready'}, other={kind:'dataset',source_id:2,status:'ready'};
 const value=withoutAttachmentSource({scope:'board',keys:[],confirmFull:true},resource,[resource,other,{kind:'image',source_id:3,status:'ready'}]);
 assert.equal(value.scope,'selected');assert.deepEqual(value.keys,['dataset:2']);
});

test('attachment send state distinguishes waiting, ready, failed and removed files',async()=>{
 const {canvasAttachmentState}=await import('./canvasAttachments.js');
 for(const status of ['selected','uploading','retrying','queued','processing'])assert.equal(canvasAttachmentState([{status}]).waiting,true);
 const ready={status:'ready'},failed={status:'error'},removed={status:'removed'};
 assert.deepEqual(canvasAttachmentState([ready,failed,removed]),{ready:[ready],failed:[failed],waiting:false});
 assert.deepEqual(canvasAttachmentState([]),{ready:[],failed:[],waiting:false});
});
