import CanvasSharing from '@kumuta/CanvasSharing.jsx';
import {mainOrigin} from './App.jsx';
import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { jsonBody } from '@kumuta/api.js';
import Modal, { ErrorNotice } from '@kumuta/Modal.jsx';
import { Autosave } from './autosave.js';
import { sceneSnapshot, downloadScene } from './scene.js';
import CanvasResourceFrames from '@kumuta/CanvasResourceFrames.jsx';
import CanvasArtifacts from './CanvasArtifacts.jsx';
import { convertToExcalidrawElements, restore, CaptureUpdateAction, newElementWith, exportToCanvas, getCommonBounds } from '@excalidraw/excalidraw';
import { generationElements } from '@kumuta/generationPlacement.js';
import BoardPanel from './BoardPanel.jsx';
import {useCanvasSidebar} from '@kumuta/CanvasSidebarControls.jsx';
import CanvasProposal from '@kumuta/CanvasProposal.jsx';
import CanvasSelection from '@kumuta/CanvasSelection.jsx';
import { useQuickUI } from '@kumuta/QuickUISettings.jsx';
import { proposalGeometry, proposalKey } from '@kumuta/canvasProposal.js';
const Drawing = lazy(() => import('./Drawing.jsx'));
const messages = {
  saved:'All changes saved', pending:'Unsaved changes', saving:'Saving…', conflict:'Save conflict', error:'Changes not saved', invalid:'Scene needs attention',
};
function saveError(error) {
  if (error?.status === 409) return 'A newer revision or an archive change prevents saving. Your local drawing is preserved. Download a recovery copy, reload, or save it as a new board.';
  if (error?.status === 413) return 'Storage limit reached. The server did not accept this scene. Download a recovery copy; reduce image/scene size or use a new board if the history limit is reached.';
  if (error?.status === 422) return `The scene was rejected as invalid. Your local drawing is preserved. ${error.message}`;
  return error?.message || '';
}
class DrawingBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (this.state.error) return <div className="editor-loading" role="alert"><h2>Drawing tools could not load</h2><p>Your saved board remains on the server. Download a recovery copy before reloading if you have unsaved work.</p><button onClick={this.props.onRecover}>Download recovery copy</button><button onClick={()=>location.reload()}>Reload editor</button></div>;
    return this.props.children;
  }
}
export default function Editor({ api, id, workspaces, navigate, registerGuard, accountId }) {
  const appearance=useQuickUI().canvasAppearance;
  const [selectionIntent,setSelectionIntent]=useState(null);
  const textStyleQueue=useRef(Promise.resolve());
  const [proposal,setProposal]=useState(null),[proposalReady,setProposalReady]=useState(false);
  const aiSession=useRef({}),focusProposal=useRef(''),currentProposal=useRef('');
  const onProposal=useCallback(next=>{
    const key=proposalKey(next);
    if(currentProposal.current!==key){setProposalReady(false);currentProposal.current=key;}
    const drawing=native.current;
    setProposal(old=>next?{...next,geometry:proposalKey(old)===key?old.geometry:drawing?proposalGeometry(next.artifact,next.version,drawing.getSceneElements(),drawing.getAppState()):null}:null);
  },[]);
  const onProposalBounds=useCallback((bounds,key)=>{
    const drawing=native.current;if(!drawing)return;
    const state=drawing.getAppState(),viewKey=`${key}:${state.width}:${state.height}`;
    if(focusProposal.current===viewKey)return;
    focusProposal.current=viewKey;
    drawing.scrollToContent(convertToExcalidrawElements([{type:'rectangle',...bounds}],{regenerateIds:true}),{fitToContent:true,viewportZoomFactor:.75});
  },[]);
  const [data, setData] = useState(null), [loadError, setLoadError] = useState(''), [reload, setReload] = useState(0);
  const sidebar = useCanvasSidebar(accountId);
  const [state, setState] = useState({status:'saved',revision:0}), [panel, setPanelState] = useState(()=>sidebar.pinned?'ai':null), [online, setOnline] = useState(navigator.onLine);
  const [dialog, setDialog] = useState(null), [actionBusy, setActionBusy] = useState(false), [actionError, setActionError] = useState('');
  const [share,setShare]=useState(false),[denied,setDenied]=useState(false);
  const resources=useRef([]),resourceRequest=useRef(null);
  useEffect(()=>()=>resourceRequest.current?.abort(),[id,api]);
  const [resourcePreview,setResourcePreview]=useState(null);
  const setPanel = next => { if(next!==null || !sidebar.pinned)setPanelState(next); };
  const dismissPanel = () => {sidebar.update({pinned:false});setPanelState(null);};
  const artifacts = useRef([]), applying = useRef(false);
  const [generationBusy,setGenerationBusy]=useState(false);
  const [visual, setVisual] = useState(null), [artifactTick, setArtifactTick] = useState(0);
  const visualKey = useRef(null);
  const saver = useRef(null), native = useRef(null), latest = useRef(null), first = useRef(true), readonly = useRef(true), decision = useRef(null);
  useEffect(() => {
    const abort = new AbortController(); let active = true; setData(null); setLoadError(''); first.current=true;
    (async () => {
      const [board, snapshot] = await Promise.all([api(`/boards/${id}`,{signal:abort.signal}),api(`/boards/${id}/scene`,{signal:abort.signal})]);
      const project = board.project_id && board.role==='owner' ? await api(`/projects/${board.project_id}`,{signal:abort.signal}) : null;
      if (!active) return;
      readonly.current = board.role==='viewer' || board.status === 'archived' || board.project_archived || !!project?.archived;
      resources.current=snapshot.scene.resources||[];setResourcePreview(null);latest.current=snapshot.scene; artifacts.current=snapshot.scene.artifacts || []; visualKey.current=null; setVisual(null);setProposal(null);setSelectionIntent(null);currentProposal.current='';focusProposal.current='';aiSession.current={};
      saver.current = new Autosave({revision:snapshot.revision, scene:snapshot.scene, onState:setState,
        save:(scene, expected_revision)=>api(`/boards/${id}/scene`,{method:'PUT',...jsonBody({expected_revision,scene})})});
      setState({status:'saved',revision:snapshot.revision}); setData({board,snapshot,project,readOnly:readonly.current});
    })().catch(e=> {if(active) setLoadError(e.message);});
    return () => {active=false;abort.abort();saver.current?.dispose();native.current=null;};
  },[api,id,reload]);
  useEffect(()=>{
    if(!data)return;
    let active=true,busy=false;
    const check=async()=>{
      if(busy)return;busy=true;
      try{
        const current=await api(`/boards/${id}`);
        if(!active)return;
        const nextReadOnly=current.role==='viewer'||current.status==='archived'||current.project_archived||!!data.project?.archived;
        readonly.current=nextReadOnly;
        setData(old=>old?{...old,board:current,readOnly:nextReadOnly}:old);
        if(nextReadOnly){setProposal(null);setPanel(old=>['history','resources'].includes(old)?old:null);}
      }catch(e){if(active&&(e.status===403||e.status===404)){readonly.current=true;setDenied(true);setProposal(null);setPanel(null);setResourcePreview(null);resourceRequest.current?.abort();}}
      finally{busy=false;}
    };
    const timer=setInterval(check,3000);window.addEventListener('focus',check);
    return()=>{active=false;clearInterval(timer);window.removeEventListener('focus',check);};
  },[api,id,!!data,data?.project?.archived]);
  const onAPI = useCallback(value => { native.current=value; }, []);
  const onChange = useCallback((elements, appState, files) => {
    latest.current={type:'excalidraw',version:2,elements,appState:Object.fromEntries(['viewBackgroundColor','gridSize','gridStep','gridModeEnabled'].map(k=>[k,appState[k]])),files,resources:resources.current,...(artifacts.current.length?{artifacts:artifacts.current}:{})};
    const key=JSON.stringify([elements.map(e=>[e.id,e.version,e.versionNonce,e.x,e.y,e.width,e.height,e.angle,e.isDeleted,e.locked]),appState.scrollX,appState.scrollY,appState.zoom,appState.width,appState.height,appState.selectedElementIds,appState.activeTool?.type]);
    if (visualKey.current!==key) {visualKey.current=key;setVisual({elements,appState});}
    setProposal(old=>old&&!old.geometry?{...old,geometry:proposalGeometry(old.artifact,old.version,elements,appState)}:old);
    const queue = saver.current;
    if (!queue || readonly.current || applying.current) return;
    try {
      const scene=sceneSnapshot(elements,appState,files,artifacts.current,resources.current);
      if (first.current) { first.current=false; queue.latest=scene; queue.saved=JSON.stringify(scene); return; }
      if (queue.error?.localValidation) queue.error=null;
      queue.change(scene);
    } catch (error) {
      first.current=false; error.localValidation=true; clearTimeout(queue.timer);
      // Do not clear a server conflict when editing an unsupported element.
      if (!queue.error) queue.error=error;
      queue.report(queue.error.status === 409 ? 'conflict' : 'invalid', queue.error);
    }
  },[]);
  const recover = useCallback(() => { if (latest.current) downloadScene(latest.current,`board-${id}-recovery`); },[id]);
  const askLeave = useCallback(async () => {
    const queue=saver.current;
    if (!queue || readonly.current) return true;
    try { await queue.flush(); return true; }
    catch {
      if (decision.current) return false;
      setActionError(''); setDialog({kind:'leave'});
      return new Promise(resolve=> {decision.current=resolve;});
    }
  },[]);
  useEffect(()=>registerGuard(askLeave),[registerGuard,askLeave]);
  useEffect(()=> {
    const before = event => { const q=saver.current; if (q && (q.dirty || q.error || q.running)) { q.flush().catch(()=>{}); event.preventDefault(); event.returnValue=''; } };
    const visibility=()=> {if(document.visibilityState==='hidden') saver.current?.flush().catch(()=>{});};
    const connected=()=>setOnline(navigator.onLine);
    window.addEventListener('beforeunload',before);document.addEventListener('visibilitychange',visibility);window.addEventListener('online',connected);window.addEventListener('offline',connected);
    return ()=> {window.removeEventListener('beforeunload',before);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('online',connected);window.removeEventListener('offline',connected);decision.current?.(false);decision.current=null;};
  },[]);
  function closeDialog() {decision.current?.(false);decision.current=null;setDialog(null);setActionError('');}
  async function act() {
    setActionBusy(true);setActionError('');
    try {
      if(dialog.kind==='leave') {decision.current?.(true);decision.current=null;setDialog(null);return;}
      if(dialog.kind==='reload') {setDialog(null);setReload(n=>n+1);return;}
      if(dialog.kind==='restore') {
        await saver.current.flush();
        await api(`/boards/${id}/revisions/${dialog.revision}/restore`,{method:'POST',...jsonBody({expected_revision:saver.current.revision})});
        setDialog(null);setReload(n=>n+1);return;
      }
      if(dialog.kind==='recovery') {
        const scene=sceneSnapshot(latest.current.elements,latest.current.appState,latest.current.files,artifacts.current,resources.current);
        const shared=data.board.role!=='owner';
        if(shared&&scene.resources?.length)throw Error('This recovery includes private source references. Download the recovery copy; original sources cannot be copied into your workspace.');
        const workspace_id=shared?workspaces[0]?.id:data.board.workspace_id;
        if(!workspace_id)throw Error('Load your own workspace before creating a recovery board. Download a recovery copy now.');
        const board=await api('/boards',{method:'POST',...jsonBody({workspace_id,...(!shared&&data.board.project_id?{project_id:data.board.project_id}:{}),title:`${data.board.title.slice(0,175)} (recovery)`})});
        try {await api(`/boards/${board.id}/scene`,{method:'PUT',...jsonBody({expected_revision:0,scene})});}
        catch(e) {throw new Error(`Recovery board #${board.id} was created, but its scene was not saved. Your local drawing is still here. ${e.message}`);}
        // Explicit recovery preserves the drawing in another board; no need to
        // resubmit the conflicted source scene during this navigation.
        saver.current.dispose();saver.current.saved=JSON.stringify(saver.current.latest);saver.current.error=null;
        setDialog(null);await navigate({boardId:board.id});
      }
    } catch(e) {
      setActionError(saveError(e));
      if (e.status===409 && dialog.kind==='restore') {saver.current.error=e;saver.current.report('conflict',e);}
    } finally {setActionBusy(false);}
  }
  async function placeGenerated(artifact, version, operation) {
    if (readonly.current || generationBusy) throw Error('This canvas is read only or an insertion is already running.');
    setGenerationBusy(true);
    try {
      // Disable native input before draining edits. Server composes only this
      // artifact into the authoritative scene under the same revision check.
      await new Promise(resolve=>requestAnimationFrame(resolve));
      await saver.current.flush();
      const drawing=native.current;if(!drawing)throw Error('Drawing tools are still loading.');
      const s=drawing.getAppState(),z=s.zoom.value;
      const all=drawing.getSceneElements(),ownIds=new Set(artifact.placement?.element_ids||(operation==='selection'?version.selection?.element_ids:[])||[]);
      const own=all.filter(e=>ownIds.has(e.id));
      const x=['replace','selection'].includes(operation)&&own.length?Math.min(...own.map(e=>e.x)):all.length?Math.max(...all.map(e=>e.x+e.width))+80:-s.scrollX+40/z;
      const y=['replace','selection'].includes(operation)&&own.length?Math.min(...own.map(e=>e.y)):all.length?Math.min(...all.map(e=>e.y)):-s.scrollY+160/z;
      const pendingBounds=proposalKey(proposal)===`${artifact.id}:${version.version}`&&!own.length?proposal?.geometry:null;
      const added=operation==='remove'?[]:generationElements(version.content,`${artifact.id}_v${version.version}`,pendingBounds?.x??x,pendingBounds?.y??y,convertToExcalidrawElements,appearance);
      if(version.engine==='B'&&operation==='replace'&&own.length===1&&own[0].type==='rectangle') {
        added[0].width=own[0].width;added[0].height=own[0].height;
      }
      const elements=sceneSnapshot(added,{},{}).elements;
      let result;
      try {
        result=await api(`/boards/${id}/artifacts/${artifact.id}/placement`,{method:'POST',...jsonBody({expected_revision:saver.current.revision,operation,version:version.version,elements})});
      } catch(e) {
        if(!e.status || e.status===409) {
          saver.current.error=e;saver.current.report(e.status===409?'conflict':'error',e);
          throw Error(`${e.message} Reload saved scene before another insertion if the request may have reached the server. Your local drawing is preserved.`);
        }
        throw e;
      }
      applying.current=true;
      resources.current=result.scene.resources||[];artifacts.current=result.scene.artifacts||[];latest.current=result.scene;setArtifactTick(n=>n+1);
      const restored=restore(result.scene,null,null),queue=saver.current;
      queue.revision=result.revision;queue.latest=result.scene;queue.saved=JSON.stringify(result.scene);queue.error=null;
      drawing.updateScene({elements:restored.elements,captureUpdate:CaptureUpdateAction.IMMEDIATELY});
      queue.report('saved');
      applying.current=false;
      const ids=new Set(elements.map(e=>e.id));
      if(ids.size)drawing.scrollToContent(restored.elements.filter(e=>ids.has(e.id)),{fitToContent:true});
    } finally {applying.current=false;setGenerationBusy(false);}
  }
  function resourceOpen(reference){setResourcePreview({id:crypto.randomUUID(),reference});setPanel('resources');}
  async function resourceAsk(reference,action,prompt){
    if(readonly.current)return;
    resourceRequest.current?.abort();const abort=new AbortController();resourceRequest.current=abort;
    const expected_revision=await saver.current.flush().then(()=>saver.current.revision);
    const request={expected_revision,resources:[reference],action};
    const context=await api(`/boards/${id}/selection/resolve`,{method:'POST',signal:abort.signal,...jsonBody(request)});
    if(abort.signal.aborted)return;
    setSelectionIntent({id:crypto.randomUUID(),context,request,prompt,...(action==='modify'?{mode:prompt.toLowerCase().includes('interactive')?'ui':'diagram'}:{})});setPanel('ai');
  }
  function patchResourceAnchor(anchorId,patch,capture=false){const drawing=native.current;if(!drawing||readonly.current)return;drawing.updateScene({elements:drawing.getSceneElementsIncludingDeleted().map(e=>e.id===anchorId?newElementWith(e,patch):e),captureUpdate:capture?CaptureUpdateAction.IMMEDIATELY:CaptureUpdateAction.NEVER});}
  async function addResource(reference){
    if(readonly.current)return;
    const drawing=native.current;if(!drawing)throw Error('Drawing tools are loading.');
    const s=drawing.getAppState(),z=s.zoom.value,all=drawing.getSceneElements();
    const anchor=convertToExcalidrawElements([{type:'rectangle',x:all.length?Math.max(...all.map(e=>e.x+e.width))+40:-s.scrollX+60/z,y:all.length?Math.min(...all.map(e=>e.y)):-s.scrollY+120/z,width:460,height:420,strokeColor:'#ff6500',backgroundColor:'#ffffff',fillStyle:'solid',roughness:0}],{regenerateIds:true})[0];
    resources.current=[...resources.current,{schema_version:1,id:crypto.randomUUID(),anchor_id:anchor.id,reference}];
    drawing.updateScene({elements:[...drawing.getSceneElementsIncludingDeleted(),anchor],captureUpdate:CaptureUpdateAction.IMMEDIATELY});
    drawing.scrollToContent([anchor],{fitToContent:true});await saver.current.flush();
  }
  function referenceChange(frameId,reference){
    if(readonly.current)return;
    resources.current=resources.current.map(f=>f.id===frameId?{...f,reference}:f);setArtifactTick(n=>n+1);
    const a=native.current;if(a)onChange(a.getSceneElementsIncludingDeleted(),a.getAppState(),a.getFiles());
  }
  if (!data) return <main className="editor-loading"><button onClick={()=>navigate({})}>← Board library</button>{loadError?<ErrorNotice error={loadError} retry={()=>setReload(n=>n+1)} />:<p role="status">Opening your canvas…</p>}</main>;
  if(denied)return <main className="page-message" role="alert"><h1>Board access unavailable</h1><p>Your access was revoked. This board is no longer available.</p><button onClick={recover}>Download unsaved recovery copy</button><button onClick={()=>navigate({})}>Back to boards</button></main>;
  const {board,project,readOnly,snapshot}=data;
  const back=()=>navigate(board.role==='owner'?{workspaceId:board.workspace_id,projectId:board.project_id}:{});
  function changeTextStyle(ids, patch) {
    const api=native.current;
    textStyleQueue.current=textStyleQueue.current.then(async()=>{
      if(!api||native.current!==api||readOnly||generationBusy||api.getAppState().viewModeEnabled)return;
      const targets=new Set(api.getSceneElementsIncludingDeleted().filter(e=>ids.includes(e.id)&&!e.locked).map(e=>e.id));
      for(const e of api.getSceneElementsIncludingDeleted().filter(e=>targets.has(e.id))){
        const family={1:'Virgil',2:'Helvetica',3:'Cascadia'}[patch.fontFamily??e.fontFamily]||'sans-serif';
        await document.fonts.load(`${patch.fontSize??e.fontSize}px "${family}"`);
      }
      if(native.current!==api||api.getAppState().viewModeEnabled)return;
      const all=api.getSceneElementsIncludingDeleted(),changed=all.map(e=>targets.has(e.id)?newElementWith(e,patch):e);
      const measured=new Map(restore({elements:structuredClone(changed),appState:{},files:{}},null,null,{refreshDimensions:true,repairBindings:true}).elements.map(e=>[e.id,e]));
      api.updateScene({elements:all.map(e=>{if(!targets.has(e.id))return e;const m=measured.get(e.id);return newElementWith(e,{...patch,...(m?{x:m.x,y:m.y,width:m.width,height:m.height,text:m.text}:{})});}),captureUpdate:CaptureUpdateAction.IMMEDIATELY});
    }).catch(error=>setActionError(error.message));
  }
  return <main className="editor-shell">
    <header className="editor-header"><button className="editor-back" aria-label="Back to board library" onClick={back}>←</button><div className="editor-title"><strong title={board.title}>{board.title}</strong><small>{workspaces.find(w=>w.id===board.workspace_id)?.name || 'Workspace'} / {project?.name || 'Canvas'}{readOnly?' · Read only':''}</small></div>
      <button className="share-action primary" onClick={()=>setShare(true)}>Share</button><a href={`${mainOrigin}/#/project/${board.project_id}/canvas`} hidden={!board.project_id||board.role!=='owner'} onClick={async e=>{e.preventDefault();try{await saver.current.flush();location.assign(`${mainOrigin}/#/project/${board.project_id}/canvas`);}catch(e){setActionError(e.message);}}}>Back to project</a><span className={`save-status ${state.status}`} role="status">{!online?'Offline · ':''}{readOnly?'Read only':messages[state.status]} <small>· v{state.revision}</small></span>
      <button aria-label="Download recovery copy" title="Download recovery copy" onClick={recover}>↓ <span className="desktop-label">Recovery</span></button><button className={panel?'selected':''} aria-label="Open board sidebar" aria-expanded={!!panel} onClick={()=>panel?dismissPanel():setPanel('ai')}>☷ <span className="desktop-label">Board details</span></button>
    </header>
    {(state.error || !online) && <div className="save-feedback" role="alert"><span>{!online?'You are offline. Keep this tab open until your changes save. ':''}{saveError(state.error)}</span><div><button onClick={recover}>Download recovery</button>{state.status!=='conflict' && state.status!=='invalid' && state.error && <button onClick={()=>saver.current.retry().catch(()=>{})}>Retry save</button>}<button onClick={()=>{setActionError('');setDialog({kind:'reload'});}}>Reload saved scene</button>{state.error && !project?.archived && <button onClick={()=>{setActionError('');setDialog({kind:'recovery'});}}>Save as new board</button>}</div></div>}
    {readOnly && <div className="readonly-notice">{board.role==='viewer'?'Viewer access · Editing and AI generation are disabled.':project?.archived?'This project is archived. Restore the project in Kumuta AI to edit.':'This board is archived. Restore it from the library to edit.'}</div>}
    <div className="editor-body"><div className="drawing-stage" aria-label="Drawing area"><DrawingBoundary key={reload} onRecover={recover}><Suspense fallback={<p role="status">Loading drawing tools…</p>}><Drawing hasArtifacts={artifacts.current.length>0} scene={snapshot.scene} readOnly={readOnly||generationBusy} onChange={onChange} onAPI={onAPI} /></Suspense></DrawingBoundary>{visual && <CanvasArtifacts key={`${id}-${reload}`} apiRef={native} visual={visual} artifacts={artifacts.current} tick={artifactTick} appearance={appearance} personalView={board.role==='viewer'} readOnly={readOnly||generationBusy} onArtifacts={change=>{artifacts.current=typeof change==='function'?change(artifacts.current):change;setArtifactTick(n=>n+1);const a=native.current;if(a) onChange(a.getSceneElementsIncludingDeleted(),a.getAppState(),a.getFiles());}} />}{visual&&<CanvasResourceFrames frames={resources.current} visual={visual} api={api} boardId={id} nativeRef={native} readOnly={readOnly||generationBusy||board.role!=='owner'} onReference={referenceChange} onAsk={async(...args)=>{try{await resourceAsk(...args);}catch(e){if(e.name!=='AbortError')setActionError(e.message);}}} onOpen={resourceOpen} patch={patchResourceAnchor} />}{actionError&&!dialog&&<div className="save-feedback" role="alert">{actionError}<button onClick={()=>setActionError('')}>Dismiss</button></div>}{visual&&<CanvasSelection artifacts={artifacts.current} resources={resources.current} onTextStyle={changeTextStyle} api={api} boardId={id} visual={visual} nativeRef={native} flush={async()=>{await saver.current.flush();return saver.current.revision;}} readOnly={readOnly||generationBusy} exportToCanvas={exportToCanvas} getCommonBounds={getCommonBounds} onIntent={intent=>{setSelectionIntent(intent);setPanel('ai');}} />}{proposal&&<CanvasProposal proposal={proposal} visual={visual} appearance={appearance} onBounds={onProposalBounds} onReady={setProposalReady} />}</div>
      {panel && <BoardPanel sidebar={sidebar} onDismiss={dismissPanel} resourcePreview={resourcePreview} onOpenResource={resourceOpen} onAddResource={addResource} onAskResource={async(...args)=>{try{await resourceAsk(...args);}catch(e){if(e.name!=='AbortError')setActionError(e.message);}}} selectionIntent={selectionIntent} session={aiSession} onProposal={onProposal} proposalReady={proposalReady} onPlace={placeGenerated} api={api} board={board} readOnly={readOnly||generationBusy} tab={panel} setTab={setPanel} revision={state.revision} onRestore={revision=>{setActionError('');setDialog({kind:'restore',revision});}} />}
    </div>
    {share&&<CanvasSharing api={api} board={board} onClose={()=>setShare(false)}/>}
    {!readOnly&&<p className="readonly-notice">{board.role==='owner'?'Saved edits and history become visible to accepted collaborators. Original sources remain private.':'Editor access · Saved edits are shared. AI uses your own Gemini key and quota. Original sources stay private.'}</p>}
    {dialog && <Modal title={{leave:'Unsaved drawing',reload:'Reload saved scene',restore:'Restore scene revision',recovery:'Save recovery board'}[dialog.kind]} onClose={closeDialog} busy={actionBusy}><div className="dialog-form"><p>{dialog.kind==='leave'?'Saving failed. Download a recovery copy before leaving. Leaving discards unsaved changes in this tab.':dialog.kind==='reload'?'Reload the latest server scene? Unsaved local changes will be discarded. Download a recovery copy first if you need them.':dialog.kind==='restore'?`Restore revision ${dialog.revision}? Pending edits will save first. Restoration creates a new revision and retains existing history.`:'Create a separate board containing your current local drawing? The original board will retain its server history.'}</p><ErrorNotice error={actionError} /><button onClick={recover}>Download recovery copy</button><footer><button onClick={closeDialog} disabled={actionBusy}>Cancel</button><button className="primary" disabled={actionBusy} onClick={act}>{actionBusy?'Working…':dialog.kind==='leave'?'Leave without saving':dialog.kind==='reload'?'Discard local and reload':dialog.kind==='restore'?'Restore as new revision':'Create recovery board'}</button></footer></div></Modal>}
  </main>;
}
