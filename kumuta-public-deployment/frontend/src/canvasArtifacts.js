import {validTableState, validFormulas} from './intelligentUI.js';
// Original D7-3 contracts. This module performs no requests and runs no code.
import { validSpec } from './quickui.js';

const object = v => v && typeof v === 'object' && !Array.isArray(v);
const keys = (v, allowed) => object(v) && Object.keys(v).every(k => allowed.includes(k));
const identity = v => typeof v === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(v);
const finite = v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= 1e12;
export const ENGINES = Object.freeze({ A: 'Native diagram', B: 'Structured QuickUI', C: 'Custom preview' });
function canvasSpec(spec) {
  const label = v => typeof v === 'string' && v.length <= 300;
  const optional = (v, check) => v === undefined || check(v);
  const fields = {markdown:['text'],table:['columns','rows','formats'],chart:['kind','labels','series','unit','colors'],cards:['items'],timeline:['items'],diagram:['syntax','text'],calculator:['operation','inputs','unit','formulas'],checklist:['items'],progress:['items'],form:['fields','submit_label']};
  return validSpec(spec) && keys(spec,['version','title','blocks']) && optional(spec.title,label) && spec.blocks.every(b =>
    keys(b,['type','title','span','sources',...fields[b.type]]) && optional(b.title,label) && optional(b.unit,label) && optional(b.span,v=>v===1||v===2) && optional(b.sources,v=>Array.isArray(v)&&v.length<=20&&v.every(n=>Number.isInteger(n)&&n>=1&&n<=100)) &&
    (b.type!=='markdown' || b.text.length<=12000) &&
    (b.type!=='table' || b.columns.every(label) && b.rows.every(r=>r.every(v=>label(v)||finite(v)))) &&
    (b.type!=='chart' || b.labels.every(label) && b.series.every(s=>keys(s,['name','values'])&&label(s.name)&&s.values.every(finite))) &&
    (b.type!=='calculator' || b.inputs.every(i=>keys(i,['label','min','max','step','value','kind','options'])&&label(i.label)&&[i.min,i.max,i.step,i.value].every(finite)) && (!['loan','compound'].includes(b.operation)||b.inputs.every(i=>i.min>=0))) &&
    (!['cards','timeline','progress','checklist'].includes(b.type) || b.items.every(i=>{
      const f={cards:['label','value','detail'],timeline:['when','title','detail'],progress:['label','value','max'],checklist:['text','checked']}[b.type];
      return keys(i,f) && f.every(k=>i[k]===undefined || (['value','max'].includes(k)?label(i[k])||finite(i[k]):k==='checked'?typeof i[k]==='boolean':label(i[k])));
    })));
}
export function validInteraction(spec, state) {
  return object(state) && Object.entries(state).every(([key, value]) => {
    if (!/^(0|[1-9][0-9]*)$/.test(key)) return false;
    const b = spec.blocks[Number(key)];
    if (!b) return false;
    if (b.type === 'form') return keys(value,['values','submitted']) && Array.isArray(value.values) && value.values.length===b.fields.length && (value.submitted===undefined||typeof value.submitted==='boolean') && value.values.every((v,i)=>['checkbox','switch'].includes(b.fields[i].kind)?typeof v==='boolean':typeof v==='string'&&v.length<=4000&&(!['select','radio'].includes(b.fields[i].kind)||b.fields[i].options.includes(v)));
    if (b.type === 'table') return validTableState(b,value);
    if (b.type === 'calculator' && object(value)) return keys(value,['values','expressions']) && Array.isArray(value.values) && value.values.length===b.inputs.length && value.values.every((v,i)=>finite(v)&&v>=b.inputs[i].min&&v<=b.inputs[i].max&&(b.inputs[i].kind!=='select'||b.inputs[i].options.includes(v))) && b.operation==='formula' && Array.isArray(value.expressions) && value.expressions.length===b.formulas.length && validFormulas(value.expressions,b.inputs.length);
    if (!Array.isArray(value)) return false;
    if (b.type === 'calculator') return value.length === b.inputs.length && value.every((v,i) => finite(v) && v >= b.inputs[i].min && v <= b.inputs[i].max && (b.inputs[i].kind!=='select'||b.inputs[i].options.includes(v)));
    if (b.type === 'checklist') return value.length === b.items.length && value.every(v => typeof v === 'boolean');
    if (b.type === 'chart') return new Set(value).size === value.length && value.every(v => Number.isInteger(v) && v >= 0 && v < b.series.length);
    return false;
  });
}
export function validArtifact(a) {
  if (!keys(a, ['id','engine','schema_version','anchor_id','capabilities','payload','state','layout','format']) || !identity(a.id) || !identity(a.anchor_id) || a.schema_version !== 1 || !Array.isArray(a.capabilities) || !object(a.state)) return false;
  if (a.engine !== 'B' && a.format !== undefined) return false;
  if (JSON.stringify(a).length > 150000) return false;
  if (a.layout !== undefined && (!keys(a.layout,['auto_width','auto_height']) || Object.values(a.layout).some(v=>typeof v!=='boolean'))) return false;
  if (a.engine === 'B') return a.capabilities.length <= 1 && a.capabilities.every(c => c === 'local-state') && (a.format===undefined||['kumuta-json-v1','openui-lang-v1'].includes(a.format)) && canvasSpec(a.payload) && validInteraction(a.payload, a.state) && (!Object.keys(a.state).length || a.capabilities.includes('local-state'));
  if (a.engine === 'C') return !a.capabilities.length && !Object.keys(a.state).length && keys(a.payload, ['html','css','javascript']) && typeof a.payload.html === 'string' && a.payload.html.length <= 60000 && ['css','javascript'].every(k => typeof a.payload[k] === 'string' && a.payload[k].length <= (k === 'css' ? 20000 : 20000));
  return false;
}
export function validAnchors(artifacts, elements) {
  return new Set(artifacts.map(a => a.id)).size === artifacts.length && new Set(artifacts.map(a => a.anchor_id)).size === artifacts.length && artifacts.every(a => {
    const e = elements.find(e => e.id === a.anchor_id);
    return validArtifact(a) && e?.type === 'rectangle' && !e.frameId && !e.groupIds?.length && e.angle === 0 && e.width >= 240 && e.width <= 2400 && e.height >= 160 && e.height <= 2400;
  });
}
export function validateManual(value) {
  if (!keys(value, ['engine','payload','capabilities','format']) || !Object.hasOwn(ENGINES, value.engine)) throw Error('Choose a supported rendering engine.');
  if (value.engine !== 'B' && value.format !== undefined) throw Error('Format metadata belongs to structured widgets.');
  if (value.engine !== 'A') {
    if (!validArtifact({id:'manual',anchor_id:'manual',schema_version:1,state:{},...value})) throw Error('Invalid widget payload or capabilities.');
    return value;
  }
  const p = value.payload;
  if (!Array.isArray(value.capabilities) || value.capabilities.length || !keys(p,['nodes','edges']) || !Array.isArray(p.nodes) || !p.nodes.length || p.nodes.length > 100 || !Array.isArray(p.edges) || p.edges.length > 200) throw Error('Invalid native diagram contract.');
  const ids = new Set();
  for (const n of p.nodes) {
    if (!keys(n,['id','type','x','y','width','height','text']) || !identity(n.id) || ids.has(n.id) || !['rectangle','diamond','ellipse'].includes(n.type) || ![n.x,n.y,n.width,n.height].every(finite) || n.width < 100 || n.width > 1200 || n.height < 50 || n.height > 1200 || typeof n.text !== 'string' || n.text.length > 200) throw Error('Invalid or duplicate native diagram node.');
    ids.add(n.id);
  }
  if (!p.edges.every(e => keys(e,['from','to']) && ids.has(e.from) && ids.has(e.to) && e.from !== e.to)) throw Error('Diagram relationships must reference distinct supplied nodes.');
  return value;
}

// Native conversion binds endpoints but does not lay arrows out for us.
export function diagramSkeleton(payload, namespace, offsetX = 0, offsetY = 0) {
  const nodes = payload.nodes.map((n,i) => ({id:`${namespace}-node-${i}`,type:n.type,x:n.x+offsetX,y:n.y+offsetY,width:n.width,height:n.height,backgroundColor:'#fff4e8',strokeColor:'#ff6500',fillStyle:'solid',roughness:0,label:{text:n.text,fontSize:18,fontFamily:2}}));
  const byId = new Map(payload.nodes.map((n,i) => [n.id,nodes[i]]));
  const boundary = (node, toward) => {
    const cx=node.x+node.width/2, cy=node.y+node.height/2, dx=toward.x+toward.width/2-cx, dy=toward.y+toward.height/2-cy;
    const nx=Math.abs(dx)/(node.width/2), ny=Math.abs(dy)/(node.height/2);
    const divisor=node.type==='ellipse'?Math.hypot(nx,ny):node.type==='diamond'?nx+ny:Math.max(nx,ny);
    const ratio=divisor ? 1/divisor : 0, distance=Math.hypot(dx,dy) || 1;
    return [cx+dx*ratio+dx/distance*8, cy+dy*ratio+dy/distance*8];
  };
  return [...nodes,...payload.edges.map((e,i)=>{
    const from=byId.get(e.from), to=byId.get(e.to);
    const start=boundary(from,to), end=boundary(to,from);
    return {id:`${namespace}-edge-${i}`,type:'arrow',x:start[0],y:start[1],points:[[0,0],[end[0]-start[0],end[1]-start[1]]],start:{id:from.id},end:{id:to.id},endArrowhead:'arrow',strokeColor:'#333333',roughness:0};
  })];
}

export function manualExample(kind) {
  const block = {
    chart:{type:'chart',kind:'bar',title:'Illustrative sales',labels:['Jan','Feb','Mar','Apr'],series:[{name:'Sales',values:[12,20,28,36]},{name:'Target',values:[15,22,30,35]}],unit:'units'},
    table:{type:'table',columns:['Task','Status','Priority'],rows:[['Research','In progress','High'],['Prototype','To do','Medium'],['Review','Done','High']]},
    cards:{type:'cards',items:[{label:'Example tasks',value:4,detail:'Illustrative manual data'},{label:'Complete',value:1,detail:'No live data connection'}]},
    calculator:{type:'calculator',operation:'product',inputs:[{label:'Quantity',min:1,max:100,value:4,step:1},{label:'Unit price',min:1,max:500,value:25,step:1}],unit:'units'},
    checklist:{type:'checklist',items:[{text:'Define goals',checked:true},{text:'Build prototype',checked:false}]},
    timeline:{type:'timeline',items:[{when:'Step 1',title:'Understand',detail:'Collect requirements'},{when:'Step 2',title:'Explore',detail:'Compare approaches'},{when:'Step 3',title:'Create',detail:'Review the result'}]},
    progress:{type:'progress',items:[{label:'Prototype',value:40,max:100}]},
  }[kind];
  if (block) return {engine:'B',capabilities:['local-state'],payload:{version:1,title:`${kind[0].toUpperCase()+kind.slice(1)} · manual example`,blocks:[block]}};
  if (kind === 'custom') return {engine:'C',capabilities:[],payload:{html:'<h1>Space to think.<br>Tools to create.</h1><p>A manual HTML/CSS preview.</p><p>Executable widgets are disabled.</p>',css:'body { padding:24px; font:16px system-ui; color:#111; background:#fff7ef; } h1 { font-size:32px; letter-spacing:-1px; }',javascript:''}};
  const nodes = kind === 'mindmap' ? [
    {id:'idea',type:'ellipse',x:240,y:160,width:180,height:80,text:'Strategy'},
    {id:'goals',type:'rectangle',x:0,y:30,width:160,height:65,text:'Define goals'},
    {id:'research',type:'rectangle',x:500,y:30,width:160,height:65,text:'Research'},
    {id:'plan',type:'diamond',x:240,y:350,width:180,height:90,text:'Plan'},
  ] : [
    {id:'start',type:'rectangle',x:0,y:60,width:160,height:70,text:kind==='architecture'?'React / Vite':'Define goals'},
    {id:'plan',type:'diamond',x:260,y:50,width:180,height:90,text:kind==='architecture'?'FastAPI':'Plan'},
    {id:'finish',type:'rectangle',x:540,y:60,width:160,height:70,text:kind==='architecture'?'SQLite':'Execute'},
  ];
  return {engine:'A',capabilities:[],payload:{nodes,edges:kind==='mindmap'?nodes.slice(1).map(n=>({from:'idea',to:n.id})):[{from:'start',to:'plan'},{from:'plan',to:'finish'}]}};
}
