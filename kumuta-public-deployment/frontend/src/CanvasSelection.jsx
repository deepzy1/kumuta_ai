import ComponentExport from './ComponentExport.jsx';
import CanvasTextToolbar from './CanvasTextToolbar.jsx';
import {selectionActions,canvasExportItems} from './canvasComponentActions.js';
import React,{useEffect,useRef,useState} from 'react';
import {jsonBody} from './api.js';
import {scenePoint,rectangle,selectionBounds,captureSelection} from './canvasSelection.js';
import './canvasSelection.css';
export default function CanvasSelection({api,boardId,visual,nativeRef,flush,onIntent,readOnly,exportToCanvas,getCommonBounds,artifacts=[],resources=[],onTextStyle}){
  const [mode,setMode]=useState(false),[region,setRegion]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[dismissed,setDismissed]=useState('');
  const layer=useRef(null),drag=useRef(null),button=useRef(null),requestAbort=useRef(null);
  useEffect(()=>()=>requestAbort.current?.abort(),[]);
  const selected=Object.keys(visual?.appState.selectedElementIds||{}).filter(id=>visual.appState.selectedElementIds[id]);
  const selectedKey=selected.slice().sort().join('|');
  useEffect(()=>setDismissed(''),[selectedKey]);
  const boxes=region||selectionBounds((visual?.elements||[]).filter(e=>selected.includes(e.id)));
  const shown=!!region||!!selected.length&&dismissed!==selectedKey;
  const touch=(action,allowBusy=false)=>event=>{event.preventDefault();event.stopPropagation();if(!busy||allowBusy)action();};
  function toggle(){if(readOnly||busy)return;setMode(old=>!old);setRegion(null);setDismissed('');setError('');}
  function cancel(){requestAbort.current?.abort();setMode(false);setRegion(null);setDismissed(selectedKey);setError('');button.current?.focus();}
  useEffect(()=>{const escape=e=>{if(e.key==='Escape'&&(mode||shown)&&!e.target.closest('textarea,input,select,[contenteditable="true"]')){cancel();}};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape);},[mode,shown,selectedKey]);
  function down(e,resize=false){if(e.button!==0||busy)return;e.preventDefault();e.stopPropagation();const rect=layer.current.getBoundingClientRect(),p=scenePoint(e.clientX,e.clientY,rect,visual.appState);drag.current=resize?{x:region.x,y:region.y}:p;setRegion(resize?region:{...p,width:0,height:0});e.currentTarget.setPointerCapture(e.pointerId);}
  function move(e){if(!drag.current)return;e.stopPropagation();const p=scenePoint(e.clientX,e.clientY,layer.current.getBoundingClientRect(),visual.appState);setRegion(rectangle(drag.current,p));}
  function up(e){e?.stopPropagation();drag.current=null;setRegion(r=>r&&r.width>2&&r.height>2?r:null);}
  async function choose(action,text,override={}){
    if(busy||readOnly)return;
    const controller=new AbortController();requestAbort.current=controller;
    setBusy(true);setError('');
    try{
      const revision=await flush();if(controller.signal.aborted)return;
      const request={expected_revision:revision,action,...(region?{region}:{element_ids:selected}),...override};
      const context=await api(`/boards/${boardId}/selection/resolve`,{method:'POST',signal:controller.signal,...jsonBody(request)});
      if(controller.signal.aborted)return;
      onIntent({id:crypto.randomUUID(),context,request,prompt:text,
        capture:()=>captureSelection(context,nativeRef.current,exportToCanvas,getCommonBounds)});
      setMode(false);setRegion(null);setDismissed(selectedKey);
    }catch(e){if(!controller.signal.aborted)setError(e.message);}finally{setBusy(false);}
  }
  useEffect(()=>{const listener=event=>{const {anchorId,blockIndex,scope,action}=event.detail||{};if(!anchorId)return;choose(action==='chart'?'derive':action==='ask'?'ask':'explain',({summarize:'Summarize',compare:'Compare',explain:'Explain',ask:'Ask about',chart:'Visualize'})[action]+' only these '+scope+' rows.',{element_ids:[anchorId],table_scopes:[{anchor_id:anchorId,block_index:blockIndex,scope}]});};document.addEventListener('kumuta-table-action',listener);return()=>document.removeEventListener('kumuta-table-action',listener);});
  const chosenArtifacts=artifacts.filter(a=>selected.includes(a.anchor_id)),chosenResources=resources.filter(r=>selected.includes(r.anchor_id));
  const actions=selectionActions(chosenArtifacts,chosenResources,selected.length);
  const exportItems=()=>canvasExportItems({elements:visual?.elements||[],artifacts,resources,selected,nativeRef,exportToCanvas});
  const state=visual?.appState,z=state?.zoom?.value||1;
  const style=boxes&&state?{left:(boxes.x+state.scrollX)*z,top:(boxes.y+state.scrollY)*z,width:Math.max(2,boxes.width*z),height:Math.max(2,boxes.height*z)}:{};
  return <><div className="ai-select-entry" onPointerDown={e=>e.stopPropagation()}><button ref={button} aria-label="AI Select" aria-pressed={mode} disabled={readOnly||busy} onTouchEnd={touch(toggle)} onClick={toggle}>✧ AI Select</button></div>
    {mode&&<div ref={layer} className="ai-region-layer" aria-label="AI region selection" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={()=>{drag.current=null;setRegion(null);}}><span className="ai-region-help">Drag a region · Escape to cancel · use native selection and Tab for keyboard access</span></div>}
    {shown&&boxes&&<><div className="ai-selection-outline" style={style} aria-hidden="true">{mode&&region&&<button className="ai-region-resize" aria-label="Resize AI region" onPointerDown={e=>{e.stopPropagation();down(e,true);}} onPointerMove={move} onPointerUp={up} />}</div><div className="ai-selection-menu" role="group" aria-label="AI selection actions" onPointerDown={e=>e.stopPropagation()} onTouchStart={e=>e.stopPropagation()} onTouchEnd={e=>e.stopPropagation()}><ComponentExport items={exportItems} /><strong>AI Select · {region?'region':`${selected.length} selected`}</strong>{actions.map(([action,label,text])=><button key={label} disabled={busy||readOnly} onTouchEnd={touch(()=>choose(action,text))} onClick={()=>choose(action,text)}>{label}</button>)}<button onTouchEnd={touch(cancel,true)} onClick={cancel}>Cancel selection</button></div></>}
    {mode&&!shown&&<button className="ai-selection-cancel" onTouchEnd={touch(cancel,true)} onClick={cancel}>Cancel selection</button>}
    {onTextStyle&&<CanvasTextToolbar elements={visual?.elements||[]} selected={selected} readOnly={readOnly} update={onTextStyle} />}
    {error&&<div role="alert" className="ai-selection-error">{error}<button onClick={()=>setError('')}>Dismiss</button></div>}
  </>;
}
