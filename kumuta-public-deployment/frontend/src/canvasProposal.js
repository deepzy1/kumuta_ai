import {componentSize} from './intelligentUI.js';
// Proposal geometry and comparisons are pure view data. Never add preview
// elements to the native scene: autosave, export, recovery and undo own it.
export const proposalKey = preview => preview ? `${preview.artifact.id}:${preview.version.version}` : '';
export function proposalGeometry(artifact, version, elements, appState) {
  const z=appState.zoom?.value||1, ownIds=new Set(artifact.placement?.element_ids||[]);
  const live=elements.filter(e=>!e.isDeleted),own=live.filter(e=>ownIds.has(e.id));
  if(version.selection&&version.selection.action!=='derive'&&!version.selection.resources?.length&&!version.selection.retrieval&&!own.length){const b=version.selection.bounds;return {...b,width:Math.max(300,b.width),height:Math.max(200,b.height)};}
  const x=own.length?Math.min(...own.map(e=>e.x)):live.length?Math.max(...live.map(e=>e.x+e.width))+80:-appState.scrollX+40/z;
  const y=own.length?Math.min(...own.map(e=>e.y)):live.length?Math.min(...live.map(e=>e.y)):-appState.scrollY+100/z;
  if(version.engine==='B')return {x,y,width:own.length===1?own[0].width:componentSize(version.content?.payload).width,height:own.length===1?own[0].height:componentSize(version.content?.payload).height};
  const nodes=version.content.payload.nodes;
  return {x,y,width:Math.max(...nodes.map(n=>n.x+n.width))-Math.min(...nodes.map(n=>n.x)),height:Math.max(...nodes.map(n=>n.y+n.height))-Math.min(...nodes.map(n=>n.y))};
}
export function proposalChanges(previous, next) {
  const native=next.engine==='A';
  const before=previous?.engine===next.engine ? native?previous.payload.nodes:previous.payload.blocks : [];
  const after=native?next.payload.nodes:next.payload.blocks;
  const key=(item,i)=>native?item.id:String(i);
  const old=new Map(before.map((item,i)=>[key(item,i),item])),current=new Set(after.map(key));
  const items=after.map((item,i)=>({key:key(item,i),label:item.text||item.title||item.type,
    status:!old.has(key(item,i))?'addition':JSON.stringify(old.get(key(item,i)))===JSON.stringify(item)?'unchanged':'modification'}));
  const removed=before.filter((item,i)=>!current.has(key(item,i))).map(item=>({label:item.text||item.title||item.type,item,status:'removal'}));
  const oldEdges=previous?.engine==='A'?previous.payload.edges||[]:[],newEdges=native?next.payload.edges||[]:[];
  const edgeKey=e=>`${e.from}→${e.to}`,oldLinks=new Map(oldEdges.map(e=>[edgeKey(e),e]));
  const edges=newEdges.map(item=>({item,status:!oldLinks.has(edgeKey(item))?'addition':JSON.stringify(oldLinks.get(edgeKey(item)))===JSON.stringify(item)?'unchanged':'modification'}));
  const removedEdges=oldEdges.filter(e=>!newEdges.some(n=>edgeKey(n)===edgeKey(e))).map(item=>({item,label:`${item.from} → ${item.to}`,status:'removal'}));
  return {items,removed,edges,removedEdges,
    additions:[...items,...edges].filter(i=>i.status==='addition').length,
    modifications:[...items,...edges].filter(i=>i.status==='modification').length,
    removals:removed.length+removedEdges.length};
}
