import {componentSize} from '@kumuta/intelligentUI.js';
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { convertToExcalidrawElements, CaptureUpdateAction, newElementWith } from '@excalidraw/excalidraw';
import StructuredUI from '@kumuta/StructuredUI.jsx';
import CustomPreview from '@kumuta/CustomPreview.jsx';
import { ENGINES, diagramSkeleton, manualExample, validateManual, validArtifact, validInteraction } from '@kumuta/canvasArtifacts.js';
import Modal from '@kumuta/Modal.jsx';
import './artifacts.css';
const groups = [
  ['Native diagrams · A', [['flowchart','Flowchart'],['mindmap','Mind map'],['architecture','Architecture']]],
  ['Interactive QuickUI · B', [['chart','Chart'],['table','Table'],['cards','KPI cards'],['calculator','Calculator'],['checklist','Checklist'],['timeline','Timeline'],['progress','Progress']]],
  ['Custom preview · C', [['custom','HTML / CSS preview']]],
];
class ArtifactBoundary extends React.Component {
  state = {failed:false};
  static getDerivedStateFromError() {return {failed:true};}
  render() {return this.state.failed ? <p role="alert">This widget could not render. Its saved definition is preserved.</p> : this.props.children;}
}
// One measured DOM surface per stable artifact. Native anchors remain the source
// of truth for position, dimensions, selection, history and autosave.
function WidgetSurface({artifact:a,anchor:e,apiRef,appearance,appState,order,selected,readOnly,personalView,panning,onChoose,onArtifact,onInsert}) {
  const content=useRef(null),header=useRef(null),latest=useRef(null),expected=useRef({width:e.width,height:e.height}),gesture=useRef(null);
  const [viewState,setViewState]=useState(null);
  useEffect(()=>setViewState(null),[a.state]);
  latest.current={a,e,onArtifact,readOnly};
  const zoom=appState.zoom?.value||1, enabled=!panning&&['selection',undefined].includes(appState.activeTool?.type);
  const layout=a.layout||{auto_width:true,auto_height:true};
  function patch(patch,capture=CaptureUpdateAction.NEVER) {
    const api=apiRef.current;if(!api||latest.current.readOnly)return;
    api.updateScene({elements:api.getSceneElementsIncludingDeleted().map(item=>item.id===e.id?newElementWith(item,patch):item),captureUpdate:capture});
  }
  useLayoutEffect(()=>{
    if(a.engine!=='B'||readOnly||e.locked||gesture.current)return;
    const changed={};
    // Changes made through native resize handles/options disable fitting on that
    // axis. Observer writes are tracked separately and never count as a user edit.
    for(const axis of ['width','height'])if(Math.abs(e[axis]-expected.current[axis])>1)changed[`auto_${axis}`]=false;
    expected.current={width:e.width,height:e.height};
    if(Object.keys(changed).length)onArtifact({layout:{...layout,...changed}});
  },[e.width,e.height]);
  useLayoutEffect(()=>{
    if(a.engine!=='B'||!content.current)return;
    let frame=0,alive=true;
    const measure=()=>{
      cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
        const current=latest.current;if(!alive||!current||current.readOnly||current.e.locked||gesture.current)return;
        const {a,e}=current,auto=a.layout||{auto_width:true,auto_height:true},node=content.current;
        const naturalWidth=Math.max(240,...Array.from(node.querySelectorAll('table,svg,fieldset')).map(n=>{
          let width=n.scrollWidth+2,parent=n.parentElement;
          while(parent&&parent!==node){const style=getComputedStyle(parent);width+=parseFloat(style.paddingLeft)||0;width+=parseFloat(style.paddingRight)||0;width+=parseFloat(style.borderLeftWidth)||0;width+=parseFloat(style.borderRightWidth)||0;parent=parent.parentElement;}
          return width;
        }));
        const width=auto.auto_width?Math.min(2400,Math.max(e.width,Math.ceil(naturalWidth))):e.width;
        // Width must settle before measuring reflowed height.
        const height=width!==e.width?e.height:auto.auto_height?Math.min(2400,Math.max(160,Math.ceil(node.getBoundingClientRect().height/zoom+(header.current?.offsetHeight||0)+2))):e.height;
        if(Math.abs(width-e.width)>1||Math.abs(height-e.height)>1){
          expected.current={width,height};patch({width,height});
        }
      });
    };
    const observer=new ResizeObserver(measure);observer.observe(content.current);
    // A font or an intrinsic table width can change without changing the outer
    // content box. Observe the actual rendered blocks as well.
    content.current.querySelectorAll('table,svg,.qui-panel').forEach(n=>observer.observe(n));
    document.fonts?.ready.then(()=>{if(alive)measure();});measure();
    return()=>{alive=false;cancelAnimationFrame(frame);observer.disconnect();};
  },[a.payload,a.layout?.auto_width,a.layout?.auto_height,e.width,appearance,zoom,readOnly,e.locked]);
  useEffect(()=>{
    const surface=content.current?.parentElement;if(!surface)return;
    const wheel=event=>{
      const table=event.target.closest('.table-scroll');
      const canScroll=(node,delta,axis)=>node&&(delta<0?node[`scroll${axis==='Y'?'Top':'Left'}`]>0:node[`scroll${axis==='Y'?'Top':'Left'}`]+node[`client${axis==='Y'?'Height':'Width'}`]<node[`scroll${axis==='Y'?'Height':'Width'}`]-1);
      if(!event.ctrlKey&&!event.metaKey&&(canScroll(surface,event.deltaY,'Y')||canScroll(table,event.deltaX||event.shiftKey&&event.deltaY,'X'))){event.stopPropagation();return;}
      const canvas=surface.closest('.drawing-stage')?.querySelector('canvas.interactive');
      if(canvas){event.preventDefault();event.stopPropagation();canvas.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,clientX:event.clientX,clientY:event.clientY,deltaX:event.deltaX,deltaY:event.deltaY,deltaMode:event.deltaMode,ctrlKey:event.ctrlKey,metaKey:event.metaKey,shiftKey:event.shiftKey,altKey:event.altKey}));}
    };
    surface.addEventListener('wheel',wheel,{passive:false});return()=>surface.removeEventListener('wheel',wheel);
  },[]);
  function choose(event){if(document.activeElement?.closest('.canvas-artifact'))document.activeElement.blur();onChoose();apiRef.current?.updateScene({appState:{selectedElementIds:event?.shiftKey?{...apiRef.current.getAppState().selectedElementIds,[e.id]:!apiRef.current.getAppState().selectedElementIds[e.id]}:{[e.id]:true}},captureUpdate:CaptureUpdateAction.NEVER});}
  function begin(event,resize=false){
    if(event.button!==0||readOnly||e.locked)return;
    event.preventDefault();event.stopPropagation();choose(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    gesture.current={pointer:event.pointerId,x:event.clientX,y:event.clientY,anchor:{...e},resize};
  }
  function move(event,finish=false,cancel=false){
    const g=gesture.current;if(!g||event.pointerId!==g.pointer)return;
    event.stopPropagation();
    const dx=(event.clientX-g.x)/zoom,dy=(event.clientY-g.y)/zoom;
    const bounds=cancel?{x:g.anchor.x,y:g.anchor.y,width:g.anchor.width,height:g.anchor.height}:g.resize?
      {width:Math.max(240,Math.min(2400,g.anchor.width+dx)),height:Math.max(160,Math.min(2400,g.anchor.height+dy))}:
      {x:g.anchor.x+dx,y:g.anchor.y+dy};
    if(g.resize)expected.current={width:bounds.width,height:bounds.height};
    patch(bounds,finish?CaptureUpdateAction.IMMEDIATELY:CaptureUpdateAction.NEVER);
    if(finish){gesture.current=null;if(g.resize&&!cancel)latest.current.onArtifact({layout:{auto_width:false,auto_height:false}});}
  }
  function keyboardGeometry(event,resize=false) {
    if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();const control=event.currentTarget;choose();control.focus();return;}
    const direction={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
    if(!direction||readOnly||e.locked)return;
    event.preventDefault();event.stopPropagation();
    const step=event.shiftKey?100:10,[dx,dy]=direction.map(value=>value*step);
    const anchor=apiRef.current?.getSceneElementsIncludingDeleted().find(item=>item.id===e.id)||e;
    if(resize){
      const bounds={width:Math.max(240,Math.min(2400,anchor.width+dx)),height:Math.max(160,Math.min(2400,anchor.height+dy))};
      expected.current=bounds;patch(bounds,CaptureUpdateAction.IMMEDIATELY);
      onArtifact({layout:{auto_width:false,auto_height:false}});
    }else patch({x:anchor.x+dx,y:anchor.y+dy},CaptureUpdateAction.IMMEDIATELY);
  }
  const stop=event=>event.stopPropagation();
  return <article data-artifact-id={a.id} data-anchor-id={e.id} aria-label={a.payload.title||'Custom HTML widget'} className={`canvas-artifact ${selected?'selected':''}`}
    onPointerDown={event=>{event.stopPropagation();onChoose();if(!event.target.closest('input,textarea,select,button,a,[contenteditable],label'))choose(event);}}
    onKeyDown={event=>{if(event.target.closest('input,textarea,select,button,a,[contenteditable]'))event.stopPropagation();}} onKeyUp={event=>{if(event.target.closest('input,textarea,select,button,a,[contenteditable]'))event.stopPropagation();}} onCopy={stop} onCut={stop} onPaste={stop} onDoubleClick={stop}

    style={{left:(e.x+appState.scrollX)*zoom,top:(e.y+appState.scrollY)*zoom,width:e.width,height:e.height,transform:`scale(${zoom})`,zIndex:order,pointerEvents:enabled?'auto':'none'}}>
    <div ref={header} className="artifact-label" role="button" tabIndex={0} aria-label={`Move ${a.payload.title||'widget'}`} onPointerDown={event=>begin(event)} onPointerMove={event=>move(event)} onPointerUp={event=>move(event,true)} onPointerCancel={event=>move(event,true,true)} aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight" onKeyDown={event=>keyboardGeometry(event)}><span aria-hidden="true">⠿</span> {a.payload.title||ENGINES[a.engine]}</div>
    <div ref={content} className="artifact-content"><ArtifactBoundary key={JSON.stringify(a.payload)}>{validArtifact(a)?a.engine==='B'?<StructuredUI onInsert={onInsert} onTableAction={context=>document.dispatchEvent(new CustomEvent('kumuta-table-action',{detail:{anchorId:e.id,blockIndex:context.blockIndex,scope:context.scope,action:context.action}}))} preferences={appearance.widget} chartColors={appearance.charts} spec={a.payload} state={personalView?(viewState??a.state):a.state} readOnly={(!personalView&&readOnly)||e.locked||!a.capabilities.includes('local-state')} onState={state=>{if(personalView){if(validInteraction(a.payload,state))setViewState(state);return;}const current=latest.current;if(current.readOnly||current.e.locked||!current.a.capabilities.includes('local-state')||!validInteraction(current.a.payload,state))return;current.onArtifact({state});}} />:<CustomPreview payload={a.payload} />:<p role="alert">Unsupported widget specification.</p>}</ArtifactBoundary></div>
    {selected&&!readOnly&&!e.locked&&<div className="artifact-resize" role="button" tabIndex={0} aria-label={`Resize ${a.payload.title||'widget'}`} aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight" onKeyDown={event=>keyboardGeometry(event,true)} onPointerDown={event=>begin(event,true)} onPointerMove={event=>move(event)} onPointerUp={event=>move(event,true)} onPointerCancel={event=>move(event,true,true)} />}
  </article>;
}
export default function CanvasArtifacts({ apiRef, visual, artifacts, readOnly, personalView=false, onArtifacts, appearance }) {
  const [mode,setMode]=useState('canvas'), [dialog,setDialog]=useState(null), [draft,setDraft]=useState(''), [error,setError]=useState('');
  const [chosen,setChosen]=useState(null), [options,setOptions]=useState(false),[panning,setPanning]=useState(false);
  useEffect(()=>{
    const keydown=event=>{if(event.code==='Space'&&!event.target.closest?.('input,textarea,select,button,[contenteditable]'))setPanning(true);};
    const keyup=event=>{if(event.code==='Space')setPanning(false);},blur=()=>setPanning(false);
    window.addEventListener('keydown',keydown);window.addEventListener('keyup',keyup);window.addEventListener('blur',blur);
    return()=>{window.removeEventListener('keydown',keydown);window.removeEventListener('keyup',keyup);window.removeEventListener('blur',blur);};
  },[]);
  const {elements, appState}=visual, zoom=appState.zoom?.value || 1;
  const visible=artifacts.filter(a=>elements.some(e=>e.id===a.anchor_id && !e.isDeleted));
  const nativeSelection=visible.find(a=>appState.selectedElementIds?.[a.anchor_id]), widgetSelection=visible.find(a=>a.id===chosen);
  const selected=widgetSelection || nativeSelection;
  useEffect(()=>{if(nativeSelection)setChosen(nativeSelection.id);else setChosen(null);},[nativeSelection?.id]);
  const anchor=selected && elements.find(e=>e.id===selected.anchor_id);
  function update(elements, appState) {apiRef.current?.updateScene({elements,appState,captureUpdate:CaptureUpdateAction.IMMEDIATELY});}
  function open(value, kind='insert') {setDraft(JSON.stringify(value,null,2));setError('');setDialog(kind);}
  function insert(value, initialState = {}) {
    validateManual(value);
    const api=apiRef.current;if (!api) throw Error('Drawing tools are still loading.');
    const state=api.getAppState(), z=state.zoom.value;
    const live=api.getSceneElements().filter(e=>!e.isDeleted);
    const x=live.length?Math.max(...live.map(e=>e.x+e.width))+80:-state.scrollX+Math.max(30,(state.width/z-640)/2), y=live.length?Math.min(...live.map(e=>e.y)):-state.scrollY+150/z;
    const namespace=crypto.randomUUID();
    if(value.engine==='A') {
      const added=convertToExcalidrawElements(diagramSkeleton(value.payload,namespace,x,y),{regenerateIds:false});
      update([...api.getSceneElementsIncludingDeleted(),...added]);api.scrollToContent(added,{fitToContent:true});
    } else {
      const e=convertToExcalidrawElements([{id:namespace,type:'rectangle',x,y,...(value.engine==='B'?componentSize(value.payload):{width:540,height:380}),strokeColor:appearance.accent,backgroundColor:'#ffffff',fillStyle:'solid',roughness:0}],{regenerateIds:false})[0];
      // Publish the native anchor first; the controlled definition follows in
      // the same synchronous turn before the debounced scene save.
      update([...api.getSceneElementsIncludingDeleted(),e],{selectedElementIds:{[e.id]:true}});
      onArtifacts([...artifacts,{id:namespace,anchor_id:e.id,schema_version:1,...value,state:initialState}]);setChosen(namespace);api.scrollToContent([e],{fitToContent:false});
    }
    setDialog(null);
  }
  function saveDraft() {try {
    const value=JSON.parse(draft);
    if(dialog==='edit') {
      const next={...selected,payload:value,state:{}};
      if(!validArtifact(next)) throw Error('Invalid widget definition.');
      onArtifacts(artifacts.map(a=>a.id===next.id?next:a));setDialog(null);
    } else insert(value);
  } catch(e) {setError(e.message);}}
  function changeAnchor(patch) {
    if(readOnly || !anchor || (anchor.locked && !Object.hasOwn(patch,'locked'))) return;
    const all=apiRef.current.getSceneElementsIncludingDeleted();
    update(all.map(e=>e.id===anchor.id?newElementWith(e,patch):e));
  }
  function duplicate() {
    try {if (!selected || anchor?.locked) return;insert({engine:selected.engine,capabilities:selected.capabilities,payload:selected.payload},structuredClone(selected.state));setOptions(false);} catch(e){setError(e.message);}
  }
  function reorder(front) {
    const all=apiRef.current.getSceneElementsIncludingDeleted(), remaining=all.filter(e=>e.id!==anchor.id);
    // Drop stale fractional indices; native Excalidraw assigns fresh order.
    update((front?[...remaining,anchor]:[anchor,...remaining]).map(e=>({...e,index:null})));
  }
  const controls=selected && <div className="artifact-options"><p>{ENGINES[selected.engine]} · {selected.payload.title || 'Manual widget'}</p>
    <button disabled={readOnly || anchor.locked} onClick={()=>{setOptions(false);open(selected.payload,'edit');}}>Edit data</button>
    <button disabled={readOnly || anchor.locked} onClick={duplicate}>Duplicate widget</button>
    <button disabled={readOnly || anchor.locked} onClick={()=>reorder(true)}>Bring to front</button>
    <button disabled={readOnly || anchor.locked} onClick={()=>reorder(false)}>Send to back</button>
    <button disabled={readOnly} onClick={()=>changeAnchor({locked:!anchor.locked})}>{anchor.locked?'Unlock widget':'Lock widget'}</button>
    {selected.engine==='B'&&<button disabled={readOnly||anchor.locked} onClick={()=>onArtifacts(items=>items.map(item=>item.id===selected.id?{...item,layout:{auto_width:true,auto_height:true}}:item))}>Fit to content</button>}
    <div className="artifact-geometry">{['x','y','width','height'].map(k=><label key={k}>{k}<input aria-label={`Widget ${k}`} type="number" disabled={readOnly || anchor.locked} value={Math.round(anchor[k])} min={k==='width'?240:k==='height'?160:undefined} max={['width','height'].includes(k)?2400:undefined} onChange={e=>{const n=Number(e.target.value);if(Number.isFinite(n) && Math.abs(n)<=1e12 && (!['width','height'].includes(k) || n>=(k==='width'?240:160) && n<=2400))changeAnchor({[k]:n});}} /></label>)}</div>
    <button className="danger" disabled={readOnly || anchor.locked} onClick={()=>{changeAnchor({isDeleted:true});setOptions(false);setChosen(null);}}>Delete widget</button>
    <small>Move or resize the native rectangle in Canvas mode. Rotation, grouping and frames are not supported for widgets.</small>
  </div>;
  return <>
    <div className="artifact-toolbar" role="toolbar" aria-label="Canvas widgets"><button disabled={readOnly} onClick={()=>{setDialog('menu');setError('');}}>＋ Add to canvas</button><div className="artifact-mode" aria-label="Interaction mode" title="Canvas: select, move and resize. Interact: focus on controls. Inputs remain usable in either mode.">{['canvas','interact'].map(m=><button key={m} aria-pressed={mode===m} onClick={()=>{setMode(m);setChosen(null);}}>{m==='canvas'?'Canvas':'Interact'}</button>)}</div><button disabled={!selected} onClick={()=>setOptions(true)}>Widget options</button></div>
    <div className={`artifact-layer ${mode}`} aria-label="Board widgets">{visible.map(a=>{
      const e=elements.find(e=>e.id===a.anchor_id);
      return <WidgetSurface key={a.id} artifact={a} anchor={e} apiRef={apiRef} appearance={appearance} appState={appState} order={elements.indexOf(e)} selected={!!appState.selectedElementIds?.[a.anchor_id]||(!Object.values(appState.selectedElementIds||{}).some(Boolean)&&selected?.id===a.id)} readOnly={readOnly} personalView={personalView} panning={panning} onChoose={()=>setChosen(a.id)} onInsert={value=>{if(!readOnly)insert(value);}}
        onArtifact={patch=>onArtifacts(items=>items.map(item=>item.id===a.id?{...item,...patch}:item))} />;
    })}</div>
    {error && !dialog && <div className="artifact-error" role="alert">{error}<button onClick={()=>setError('')}>Dismiss</button></div>}
    {dialog && <Modal title={dialog==='menu'?'Add to canvas':dialog==='edit'?'Edit widget data':'Manual artifact'} onClose={()=>setDialog(null)}><div className="artifact-dialog">{dialog==='menu'?<><p>Manual examples · no AI calls. All example values are illustrative.</p>{groups.map(([title,items])=><section key={title}><h3>{title}</h3><div className="artifact-insert-grid">{items.map(([kind,label])=><button key={kind} onClick={()=>{try{insert(manualExample(kind));}catch(e){setError(e.message);}}}>{label}</button>)}</div></section>)}<button onClick={()=>open(manualExample('chart'))}>Paste a manual specification</button><small>Custom JavaScript is unavailable. Open the AI tab to generate supported diagrams and structured UI. Use Export in the component or selection toolbar for images, PDF and ZIP. Native editor export includes drawing elements only.</small></>:<><p>{dialog==='edit'?'Edit the declarative payload. Applying resets this widget’s interaction state.':'Choose engine A, B or C with a bounded payload and explicit capabilities.'}</p><textarea aria-label="Artifact JSON" spellCheck={false} value={draft} onChange={e=>setDraft(e.target.value)} maxLength={150000} /><button className="primary" onClick={saveDraft}>Apply artifact</button></>}{error && <p role="alert">{error}</p>}</div></Modal>}
    {options && selected && <Modal title="Widget options" drawer={true} onClose={()=>setOptions(false)}>{controls}</Modal>}
  </>;
}
