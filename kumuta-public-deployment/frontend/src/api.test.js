import assert from "node:assert/strict";
import test from "node:test";
import { readEvents } from "./stream.js";

test("SSE preserves split Unicode, event order and errors", async () => {
  const stream = new TextEncoder().encode(
    'event: start\ndata: {"model":"test"}\n\nevent: delta\ndata: {"text":"Hello 世界"}\n\nevent: error\ndata: {"message":"quota"}\n\nevent: done\ndata: {"status":"error"}\n\n',
  );
  let index = 0;
  const body = new ReadableStream({
    pull(controller) {
      if (index === stream.length) controller.close();
      else controller.enqueue(stream.slice(index, ++index));
    },
  });
  const received = [];
  await readEvents(new Response(body), (event, data) =>
    received.push([event, data]),
  );
  assert.deepEqual(
    received.map(([type]) => type),
    ["start", "delta", "error", "done"],
  );
  assert.equal(received[1][1].text, "Hello 世界");
});

test("SSE detects an interrupted connection without a done event", async () => {
  await assert.rejects(
    readEvents(
      new Response('event: delta\ndata: {"text":"partial"}\n\n'),
      () => {},
    ),
    /connection ended/,
  );
});

test("SSE surfaces backend preflight errors", async () => {
  const response = new Response(
    JSON.stringify({ detail: "Add your API key" }),
    { status: 428 },
  );
  await assert.rejects(
    readEvents(response, () => {}),
    /Add your API key/,
  );
});

import { readFile } from 'node:fs/promises';
// Load the real request implementation with only Vite's URL constant substituted.
let source=await readFile(new URL('./api.js',import.meta.url),'utf8');
source=source.replaceAll('"./stream"',JSON.stringify(new URL('./stream.js',import.meta.url).href)).replace('import.meta.env.VITE_API_URL','"http://offline.test"');
source=source.replace("'./canvasSceneFiles.js'",JSON.stringify(new URL('./canvasSceneFiles.js',import.meta.url).href));
const {request}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
test('cancelled JSON body reads propagate AbortError rather than empty successful state',async()=>{
 const original=globalThis.fetch;
 globalThis.fetch=async()=>({ok:true,json:async()=>{throw new DOMException('Cancelled','AbortError');}});
 try{await assert.rejects(request('','/job'),e=>e.name==='AbortError');}finally{globalThis.fetch=original;}
});
test('malformed success bodies cannot replace a saved job with an empty object',async()=>{
 const original=globalThis.fetch;
 globalThis.fetch=async()=>({ok:true,json:async()=>{throw new SyntaxError('Truncated JSON');}});
 try{await assert.rejects(request('','/job'),/unreadable response/);}finally{globalThis.fetch=original;}
});
test('valid job responses and server errors preserve their existing contracts',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async()=>({ok:true,json:async()=>({id:'saved-job',status:'completed'})});
  assert.deepEqual(await request('','/job'),{id:'saved-job',status:'completed'});
  globalThis.fetch=async()=>({ok:false,status:429,json:async()=>({detail:'Wait for your current job.'})});
  await assert.rejects(request('','/job'),e=>e.status===429&&e.message==='Wait for your current job.');
 }finally{globalThis.fetch=original;}
});
