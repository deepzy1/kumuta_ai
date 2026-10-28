import { test } from 'node:test';import assert from 'node:assert/strict';import {sceneSnapshot} from './scene.js';import {readRoute,routeHash,visibleBoards} from './navigation.js';
test('image IDs/data and native geometry survive; runtime state and orphaned files do not persist',()=>{
 const file={id:'img',mimeType:'image/png',dataURL:'data:image/png;base64,abc',created:1,lastRetrieved:9};
 const elements=[{id:'a',type:'image',x:1,y:2,width:4,height:5,fileId:'img',customData:null}];
 const result=sceneSnapshot(elements,{viewBackgroundColor:'#ffffff',scrollX:900,selectedElementIds:{a:true},collaborators:new Map()}, {img:file,unused:{id:'unused'}});
 assert.equal(result.elements[0].fileId,'img');assert.equal(result.elements[0].x,1);assert.equal(result.files.img.dataURL,file.dataURL);assert.deepEqual(result.appState,{viewBackgroundColor:'#ffffff'});assert.equal(result.files.img.lastRetrieved,undefined);assert.equal(result.elements[0].customData,undefined);assert.equal(result.files.unused,undefined);
});
test('missing images and unsupported embeds/customData fail without silently dropping drawing content',()=>{
 assert.throws(()=>sceneSnapshot([{type:'image',fileId:'missing'}]),/image/);assert.throws(()=>sceneSnapshot([{type:'embeddable'}]),/unsupported/);assert.throws(()=>sceneSnapshot([{type:'rectangle',customData:{script:'x'}}]),/unsupported/);
});
test('deleted images remain available for native undo',()=>{assert.equal(sceneSnapshot([{type:'image',fileId:'i',isDeleted:true}],{},{i:{id:'i',mimeType:'image/png'}}).files.i.id,'i');});
test('library is default; deep links accept safe numeric IDs only',()=>{
 assert.deepEqual(readRoute(''),{workspaceId:null,projectId:null});assert.deepEqual(readRoute('#/board/12'),{boardId:12});assert.equal(readRoute('#/board/9007199254740992').boardId,undefined);
 for(const route of [{workspaceId:3,projectId:8},{boardId:9}])assert.deepEqual(readRoute(routeHash(route)),route);
 assert.equal(routeHash({boardId:4}).includes('token'),false);
});
test('search/sort operates over loaded results without mutating API order',()=>{
 const rows=[{id:1,title:'Beta',updated_at:'2026-01',created_at:'2026-01'},{id:2,title:'Alpha',updated_at:'2026-02',created_at:'2026-02'}];assert.deepEqual(visibleBoards(rows,'a','name').map(b=>b.id),[2,1]);assert.deepEqual(rows.map(b=>b.id),[1,2]);assert.equal(visibleBoards(rows,'missing','updated').length,0);
});
