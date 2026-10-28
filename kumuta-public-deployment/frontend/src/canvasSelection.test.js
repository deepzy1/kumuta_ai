import test from 'node:test';
import assert from 'node:assert/strict';
import {scenePoint,rectangle,selectionBounds,capturePlan} from './canvasSelection.js';
test('mouse/touch scene coordinates account for pan, zoom and stage offset',()=>{
 for(const z of [.25,1,2.5]){const p=scenePoint(150,90,{left:50,top:40},{zoom:{value:z},scrollX:20,scrollY:-10});assert.deepEqual(p,{x:100/z-20,y:50/z+10});}
 assert.deepEqual(rectangle({x:20,y:30},{x:-5,y:-10}),{x:-5,y:-10,width:25,height:40});
});
test('mixed selection bounds include rotated elements and exclude tombstones',()=>{
 const b=selectionBounds([{id:'a',x:0,y:0,width:100,height:20,angle:Math.PI/2},{x:999,y:999,width:200,height:200,isDeleted:true}]);
 assert(Math.abs(b.x-40)<.001);assert(Math.abs(b.y+40)<.001);assert(Math.abs(b.width-20)<.001);assert(Math.abs(b.height-100)<.001);
 assert.equal(selectionBounds([]),null);
});
test('bounded visual crop uses scene units independent of zoom and limits DPR pixels',()=>{
 for(const dpr of [1,2,4]){const p=capturePlan({x:-100,y:50,width:4000,height:2000},{x:0,y:100,width:3000,height:1800},dpr);assert(p.width*p.height<=2000000);assert(p.width<=1600);assert.equal(p.dx,-100*p.scale);assert.equal(p.dy,-50*p.scale);}
 assert.throws(()=>capturePlan({x:0,y:0,width:1,height:1},{x:NaN,y:0,width:1,height:1}));
});
