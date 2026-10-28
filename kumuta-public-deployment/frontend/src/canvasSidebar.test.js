import test from 'node:test';
import assert from 'node:assert/strict';
import {sidebarPreference,saveSidebarPreference,sidebarKey,boundedWidth} from './canvasSidebar.js';
test('Canvas pin and width restore only for the authenticated account',()=>{
  const saved=new Map(),storage={getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v)};
  saveSidebarPreference(storage,17,{pinned:true,width:480});
  assert.deepEqual(sidebarPreference(storage,17),{pinned:true,width:480});
  assert.deepEqual(sidebarPreference(storage,18),{pinned:false,width:360});
  assert.equal(sidebarKey(null),null);assert.equal(sidebarKey('17'),null);
  saveSidebarPreference(storage,null,{pinned:true,width:500});assert.equal(saved.size,1);
  saveSidebarPreference(storage,17,{pinned:false,width:360});assert.deepEqual(sidebarPreference(storage,17),{pinned:false,width:360});
});
test('damaged or unavailable preference storage and invalid widths fail safely',()=>{
  assert.deepEqual(sidebarPreference({getItem:()=>'{bad'},2),{pinned:false,width:360});
  assert.deepEqual(sidebarPreference({getItem:()=>{throw Error('blocked');}},2),{pinned:false,width:360});
  assert.equal(boundedWidth(0),300);assert.equal(boundedWidth(10000),640);assert.equal(boundedWidth(NaN),360);
});
