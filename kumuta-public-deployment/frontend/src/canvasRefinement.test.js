import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULTS } from './quickui.js';
import { CANVAS_DEFAULTS, canvasAppearance } from './canvasAppearance.js';
import { proposalChanges, proposalGeometry } from './canvasProposal.js';
import { generationElements } from './generationPlacement.js';
import { manualExample } from './canvasArtifacts.js';

test('legacy preferences inherit; saved Canvas overrides separate UI, widget and chart palettes',()=>{
  const prefs={...DEFAULTS,color:{...DEFAULTS.color,mode:'solid',colors:['#16804a']},density:'compact'};
  assert.equal(canvasAppearance(prefs).accent,'#16804a');
  assert.deepEqual(canvasAppearance(prefs).charts,['#16804a']);
  assert.equal(canvasAppearance(prefs).widget.density,'compact');
  const canvas={...CANVAS_DEFAULTS,inherit:false,accent:'#7c3aed',widget_color:{...DEFAULTS.color,mode:'solid',colors:['#008800']},chart_colors:['#123456','#654321'],density:'spacious'};
  const resolved=canvasAppearance({...prefs,canvas});
  assert.equal(resolved.accent,'#7c3aed');assert.equal(resolved.widget.color.colors[0],'#008800');
  assert.deepEqual(resolved.charts,canvas.chart_colors);assert.equal(resolved.widget.density,'spacious');
  assert.equal(prefs.color.colors[0],'#16804a');
  assert.equal(canvasAppearance({...prefs,canvas:{...canvas,inherit:true}}).accent,'#16804a');
  assert.equal(canvasAppearance(DEFAULTS,true).widget.appearance,'dark');
});
test('proposal geometry follows the viewport and target; never mutates accepted scene',()=>{
  const version={engine:'B'},artifact={placement:{element_ids:['accepted']}},elements=[{id:'accepted',x:50,y:80,width:640,height:400}];
  const before=JSON.stringify(elements),state={zoom:{value:2},scrollX:5,scrollY:10};
  assert.deepEqual(proposalGeometry(artifact,version,elements,state),{x:50,y:80,width:640,height:400});
  assert.equal(proposalGeometry({},version,elements,state).x,770);
  assert.deepEqual(proposalGeometry({},version,[],state),{x:15,y:40,width:540,height:380});
  assert.equal(JSON.stringify(elements),before);
});
test('replacement marks additions, modifications and removals with logical IDs',()=>{
  const old={engine:'A',payload:{nodes:[{id:'a',text:'old'},{id:'b',text:'removed'}]}};
  const next={engine:'A',payload:{nodes:[{id:'a',text:'new'},{id:'c',text:'added'}]}};
  const delta=proposalChanges(old,next);
  assert.deepEqual([delta.additions,delta.modifications,delta.removals],[1,1,1]);
  assert.equal(delta.removed[0].label,'removed');
  const b=manualExample('chart');assert.equal(proposalChanges(b,b).items[0].status,'unchanged');
});
test('acceptance materializes the saved widget palette with white surfaces and dark labels',()=>{
  const appearance=canvasAppearance({...DEFAULTS,color:{...DEFAULTS.color,mode:'solid',colors:['#16804a']}});
  let skeleton;
  generationElements(manualExample('architecture'),'a'.repeat(32)+'_v1',0,0,items=>{skeleton=items;return items;},appearance);
  assert.equal(skeleton[0].strokeColor,'#16804a');assert.equal(skeleton[0].backgroundColor,'#ffffff');assert.equal(skeleton[0].label.strokeColor,'#111111');
});
