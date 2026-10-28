import React, { useEffect, useRef, useState } from 'react';
import { jsonBody, readEvents } from './api.js';
import { generationLabel, generationRequest, pendingJob } from './canvasGeneration.js';
import { proposalKey } from './canvasProposal.js';
import CanvasAppearance from './CanvasAppearance.jsx';
import Markdown from './Markdown.jsx';
import AttachmentPreview from './AttachmentPreview.jsx';
import CanvasModelPicker from './CanvasModelPicker.jsx';
import CanvasComposerPopover from './CanvasComposerPopover.jsx';
import CanvasIntelligence from './CanvasIntelligence.jsx';
import {DEFAULT_INTELLIGENCE,intelligenceSelection,resolveSourceAction,sourceSummary,automaticSourceAction,applicableActions,intelligenceReferences,SOURCE_ACTION_LABELS} from './canvasIntelligence.js';
import { clipboardImages } from './attachments.js';
import {CANVAS_ACCEPT,CANVAS_TYPES,attachmentKind,validateCanvasFiles,withoutAttachmentSource,canvasAttachmentState} from './canvasAttachments.js';
import {resourceKey} from './canvasResources.js';
import { ArrowUp, Plus, Scan } from 'lucide-react';
import './canvasGeneration.css';
import './canvasSelection.css';
const mainOrigin=import.meta.env.VITE_KUMUTA_APP_URL || (location.pathname==='/canvas.html'?location.origin:`${location.protocol}//${location.hostname}:5173`);
export default function CanvasAI({headerControls=null,api,board,readOnly,onPlace,revision,session,onProposal,proposalReady,onClose,view='ai',onView=()=>{},onBack=()=>onView('ai'),selectionIntent=null,onResource=()=>{}}) {
  const base=`/boards/${board.id}`;
  const remembered=session?.current||{};
  const [prompt,setPrompt]=useState(remembered.prompt||''),[engine,setEngine]=useState(remembered.engine||'auto'),[jobs,setJobs]=useState([]),[artifacts,setArtifacts]=useState([]);
  const [job,setJob]=useState(remembered.job||null),[selected,setSelected]=useState(remembered.selected||null),[preview,setPreview]=useState(remembered.preview||null),[ready,setReady]=useState(false);
  const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[streamError,setStreamError]=useState('');
  const [notice,setNotice]=useState('');
  const [outputFormat,setOutputFormat]=useState(remembered.outputFormat||'auto'),[openuiEnabled,setOpenuiEnabled]=useState(false);
  const [conversationId,setConversationId]=useState(remembered.conversationId),[chats,setChats]=useState([]),[chatJobs,setChatJobs]=useState([]),[chatMore,setChatMore]=useState(false),[messages,setMessages]=useState([]),[messagesMore,setMessagesMore]=useState(false);
  const chatSessions=useRef(remembered.chatSessions||{}),conversationRef=useRef(conversationId),scrollTop=useRef(remembered.scrollTop||0);
  conversationRef.current=conversationId;
  const settingsOpen=view==='settings',historyOpen=view==='generations';
  const handled=useRef(new Set(remembered.handled||[])),feed=useRef(null);
  const [more,setMore]=useState(false),[model,setModel]=useState(null),[modelError,setModelError]=useState('');
  const [mode,setMode]=useState(remembered.mode||'auto'),[files,setFiles]=useState(remembered.files||[]),[uploadProgress,setUploadProgress]=useState(null),[dragging,setDragging]=useState(false),[preferenceBusy,setPreferenceBusy]=useState(false);
  const [selection,setSelection]=useState(remembered.selection||null),[selectionVisual,setSelectionVisual]=useState(remembered.selectionVisual||false);
  const [intelligence,setIntelligence]=useState(remembered.intelligence||DEFAULT_INTELLIGENCE),[intelligenceResources,setIntelligenceResources]=useState([]);
  const [resourceFiles,setResourceFiles]=useState((remembered.resourceFiles||[]).map(f=>['uploading','retrying'].includes(f.status)?{...f,status:f.resource?'queued':'error',error:f.resource?'':'Upload interrupted. Retry safely; existing matching files are reused.'}:f));
  const [sendWaiting,setSendWaiting]=useState(false),[confirmFailed,setConfirmFailed]=useState(false);
  const sendQueued=useRef(false),submissionLock=useRef(false);
  const resourceUploads=useRef(new Map()),draftFiles=useRef([]);
  draftFiles.current=[...files,...resourceFiles];
  const consumedSelection=useRef(remembered.consumedSelection);
  useEffect(()=>{if(!selectionIntent||consumedSelection.current===selectionIntent.id)return;consumedSelection.current=selectionIntent.id;setIntelligence(DEFAULT_INTELLIGENCE);setSelection(selectionIntent);setSelectionVisual(!selectionIntent.context.resources?.length&&selectionIntent.context.visual_required);setPrompt(selectionIntent.prompt);if(selectionIntent.mode)setMode(selectionIntent.mode);setSelected(null);setFiles([]);setResourceFiles([]);draftFiles.current=[];resourceUploads.current.forEach(c=>c.abort());pendingRequest.current=null;onView('ai');requestAnimationFrame(()=>document.getElementById('canvas-ai-prompt')?.focus());},[selectionIntent?.id]);
  const promptInput=useRef(null),sourceTrigger=useRef(null);
  useEffect(()=>{
    const input=promptInput.current;
    if(!input||view!=='ai')return;
    const resize=()=>{input.style.height='auto';input.style.height=`${Math.min(input.scrollHeight,140)}px`;};
    resize();
    let width=input.clientWidth;
    const observer=new ResizeObserver(()=>{if(input.clientWidth!==width){width=input.clientWidth;resize();}});observer.observe(input.parentElement);
    return()=>observer.disconnect();
  },[prompt,view]);
  const fileInput=useRef(null),uploadController=useRef(null);
  useEffect(()=>()=>uploadController.current?.abort(),[]);
  async function loadModels(refresh=false,signal){
    try{const result=await api(`/models${refresh?'?refresh=true':''}`,{signal});if(signal?.aborted)return;setModel(result);setModelError('');if(!refresh)setMode(result.canvas_mode||'auto');}
    catch(e){if(!signal?.aborted)setModelError(e.message);}
  }
  useEffect(()=>{const abort=new AbortController();loadModels(false,abort.signal);return()=>abort.abort();},[api,board.id]);
  async function chooseModel(id){setPreferenceBusy(true);setModelError('');try{await api('/settings/model',{method:'PATCH',...jsonBody({model:id})});setModel(old=>({...old,selected:id}));pendingRequest.current=null;}catch(e){setModelError(e.message);}finally{setPreferenceBusy(false);}}
  async function chooseMode(next){setPreferenceBusy(true);setModelError('');try{await api('/settings/canvas',{method:'PATCH',...jsonBody({mode:next})});setMode(next);pendingRequest.current=null;}catch(e){setModelError(e.message);}finally{setPreferenceBusy(false);}}
  function addFiles(incoming){
    if(disabled||selection)return;
    if(board.role && board.role!=='owner' && incoming.some(file=>attachmentKind(file)!=='image')){setError('Source documents stay private to the board owner. You can send your own PNG/JPEG chat images.');return;}
    const issue=validateCanvasFiles(draftFiles.current.map(f=>f.file),incoming);
    if(issue){setError(issue);return;}
    const entries=incoming.map(file=>({id:crypto.randomUUID(),file,status:attachmentKind(file)==='image'?'attached':'uploading',progress:0}));
    draftFiles.current=[...draftFiles.current,...entries];
    setFiles(old=>[...old,...entries.filter(f=>attachmentKind(f.file)==='image')]);
    const resources=entries.filter(f=>attachmentKind(f.file)!=='image');
    setResourceFiles(old=>[...old,...resources]);setError('');pendingRequest.current=null;
    // Sequential resource requests respect the existing parser queue limits.
    (async()=>{for(const entry of resources){if(!mounted.current)break;if(!draftFiles.current.some(f=>f.id===entry.id))continue;await uploadResource(entry);}})();
  }
  function updateResourceFile(id,patch){if(mounted.current)setResourceFiles(old=>old.map(f=>f.id===id?{...f,...patch}:f));}
  async function uploadResource(entry){
    const abort=new AbortController();resourceUploads.current.set(entry.id,abort);
    updateResourceFile(entry.id,{status:'uploading',error:'',progress:0});
    try{
      const body=new FormData();body.append('file',entry.file);
      const resource=await api(base+'/resource-library/upload',{method:'POST',body,signal:abort.signal,onUploadProgress:progress=>updateResourceFile(entry.id,{progress})});
      if(abort.signal.aborted||!mounted.current)return;
      updateResourceFile(entry.id,{resource,status:resource.status,error:resource.error,progress:100});
      setIntelligenceResources(old=>[...old.filter(r=>resourceKey(r)!==resourceKey(resource)),resource]);
      setIntelligence(old=>({...old,scope:old.scope==='selection'?'selected':old.scope==='resource'?'selected':old.scope,
        keys:[...new Set([...old.keys,resourceKey(resource)])],operation:'ask',automatic:true,fullDocument:false,confirmFull:false,analyses:[]}));
      pendingRequest.current=null;
    }catch(e){if(!abort.signal.aborted)updateResourceFile(entry.id,{status:'error',error:e.message});}
    finally{if(resourceUploads.current.get(entry.id)===abort)resourceUploads.current.delete(entry.id);}
  }
  function removeResourceFile(entry){
    resourceUploads.current.get(entry.id)?.abort();
    draftFiles.current=draftFiles.current.filter(f=>f.id!==entry.id);
    setResourceFiles(old=>old.filter(f=>f.id!==entry.id));
    if(!draftFiles.current.some(f=>f.resource&&entry.resource&&resourceKey(f.resource)===resourceKey(entry.resource)))setIntelligence(old=>withoutAttachmentSource(old,entry.resource,intelligenceResources));
    pendingRequest.current=null;setNotice('Removed from this draft. Uploaded originals remain in this board’s Resources.');
  }
  async function retryResourceFile(entry){
    if(!entry.resource)return uploadResource(entry);
    const r=entry.resource;updateResourceFile(entry.id,{status:'retrying',error:''});
    try{await api(`${base}/resource-library/${r.kind}/${r.source_id}/retry`,{method:'POST'});updateResourceFile(entry.id,{status:'queued',error:''});}
    catch(e){updateResourceFile(entry.id,{status:'error',error:e.message});}
  }
  const attachmentState=canvasAttachmentState(resourceFiles),processingResources=attachmentState.waiting;
  useEffect(()=>{
    if(sendQueued.current&&!processingResources){sendQueued.current=false;setSendWaiting(false);beginSend();}
  },[processingResources,resourceFiles]);
  function cancelSend(){sendQueued.current=false;setSendWaiting(false);}
  function beginSend(){
    if(attachmentState.failed.length){setConfirmFailed(true);return;}
    setConfirmFailed(false);submit(selected?.id);
  }
  function requestSend(){
    if(disabled||submissionLock.current||sendQueued.current)return;
    if(processingResources){sendQueued.current=true;setSendWaiting(true);setConfirmFailed(false);return;}
    beginSend();
  }
  useEffect(()=>{
    if(!resourceFiles.some(f=>['queued','processing'].includes(f.status)))return;
    const abort=new AbortController();
    const poll=async()=>{try{
      const result=await api(base+'/resource-library',{signal:abort.signal});if(abort.signal.aborted)return;
      setIntelligenceResources(result.items);
      setResourceFiles(old=>old.map(f=>{if(!f.resource)return f;const r=result.items.find(r=>resourceKey(r)===resourceKey(f.resource));
        return r?{...f,resource:r,status:r.status,error:r.error}:{...f,status:'error',error:'Resource is no longer linked. Remove this attachment and upload or link it again.'};}));
    }catch(e){if(!abort.signal.aborted)setError(e.message);}};
    const timer=setInterval(poll,1500);poll();return()=>{clearInterval(timer);abort.abort();};
  },[api,board.id,resourceFiles.some(f=>['queued','processing'].includes(f.status))]);
  useEffect(()=>()=>resourceUploads.current.forEach(c=>c.abort()),[]);
  const pendingRequest=useRef(remembered.pendingRequest||null),copyKeys=useRef(remembered.copyKeys||new Map()),mounted=useRef(true),jobRef=useRef(null);
  jobRef.current=job;
  // Kept in the mounted board only; no draft, credentials or chat data is
  // written to browser storage. Closing the panel or switching tabs keeps it.
  useEffect(()=>{if(session)session.current={resourceFiles,intelligence,consumedSelection:consumedSelection.current,selection,selectionVisual,prompt,engine,mode,files,outputFormat,job,selected,preview,handled:[...handled.current],pendingRequest:pendingRequest.current,copyKeys:copyKeys.current,conversationId,chatSessions:chatSessions.current,scrollTop:feed.current?.scrollTop||scrollTop.current};},[session,resourceFiles,intelligence,selection,selectionVisual,prompt,engine,mode,files,outputFormat,job,selected,preview,busy,conversationId]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  async function refresh(append=false,signal) {
    const cid=conversationRef.current;
    const [result,saved,linked]=await Promise.all([
      api(`${base}/generations?limit=20&offset=${append?jobs.length:0}`,{signal}),
      api(`${base}/artifacts?limit=100`,{signal}),api(`${base}/conversations`,{signal})]);
    while(saved.has_more){const page=await api(`${base}/artifacts?limit=100&offset=${saved.items.length}`,{signal});saved.items.push(...page.items);saved.has_more=page.has_more;}
    if(signal?.aborted||!mounted.current||cid!==conversationRef.current)return;
    setOpenuiEnabled(!!result.openui_enabled);
    setJobs(old=>append?[...old,...result.items.filter(r=>!old.some(j=>j.id===r.id))]:result.items);setMore(result.has_more);setArtifacts(saved.items);setChats(linked.items);
    if(cid===undefined){setConversationId(linked.items[0]?.conversation_id??result.items[0]?.conversation_id??null);return;}
    const thread=await api(`${base}/generations?limit=100&${cid==null?'unassigned=true':`conversation_id=${cid}`}`,{signal});
    if(signal?.aborted||cid!==conversationRef.current)return;
    const linkedMessages=cid==null?{messages:[],has_more:false}:await api(`/conversations/${cid}?limit=100`,{signal});
    if(signal?.aborted||cid!==conversationRef.current)return;
    setChatJobs(thread.items);setChatMore(thread.has_more);setMessages(linkedMessages.messages);setMessagesMore(linkedMessages.has_more);
    const active=thread.items.find(pendingJob);
    if(active)setJob(active);
    else if(!jobRef.current&&thread.items[0])setJob(thread.items[0]);
    setPreview(old=>{const current=old&&saved.items.find(a=>a.id===old.artifact.id);return current?{...old,artifact:current}:old;});
  }
  function rememberChat(){
    chatSessions.current[String(conversationRef.current)]={resourceFiles,intelligence,selection,selectionVisual,prompt,engine,files,selected,preview,job,notice,scrollTop:feed.current?.scrollTop||0};
  }
  function switchChat(cid){
    if(active||processingResources)return;
    rememberChat();const old=chatSessions.current[String(cid)]||{};
    setIntelligence(old.intelligence||DEFAULT_INTELLIGENCE);
    conversationRef.current=cid;setConversationId(cid);setChatJobs([]);setMessages([]);setMessagesMore(false);setSelection(old.selection||null);setSelectionVisual(old.selectionVisual||false);setPrompt(old.prompt||'');setFiles(old.files||[]);setResourceFiles(old.resourceFiles||[]);setEngine(old.engine||'auto');setSelected(old.selected||null);setPreview(old.preview||null);setJob(old.job||null);jobRef.current=old.job||null;setNotice(old.notice||'');setError('');pendingRequest.current=null;scrollTop.current=old.scrollTop||0;onView('ai');
    requestAnimationFrame(()=>{if(feed.current)feed.current.scrollTop=scrollTop.current;});
  }
  async function createChat(){const row=await api(`${base}/conversations/new`,{method:'POST'});setChats(old=>[row,...old]);return row.conversation_id;}
  function newChat(){return run(async()=>{const cid=await createChat();switchChat(cid);});}
  async function olderLinkedMessages(){const cid=conversationRef.current;const result=await api(`/conversations/${cid}?limit=100&before=${messages[0].id}`);if(cid===conversationRef.current){setMessages(old=>[...result.messages,...old]);setMessagesMore(result.has_more);}}
  async function olderMessages(){const cid=conversationRef.current;const result=await api(`${base}/generations?limit=100&offset=${chatJobs.length}&${cid==null?'unassigned=true':`conversation_id=${cid}`}`);if(cid===conversationRef.current){setChatJobs(old=>[...old,...result.items]);setChatMore(result.has_more);}}

  useEffect(()=>{
    const abort=new AbortController();setLoading(true);
    refresh(false,abort.signal).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});
    return()=>abort.abort();
  },[api,board.id,revision,conversationId]);
  useEffect(()=>{
    if(!pendingJob(job))return;
    const abort=new AbortController();let cursor=0;
    (async()=>{
      while(!abort.signal.aborted){
        try{
          const response=await api(`${base}/generations/${job.id}/events?after=${cursor}`,{responseType:'stream',signal:abort.signal});
          await readEvents(response,(type,data)=>{
            if(abort.signal.aborted)return;
            if(data.sequence)cursor=Math.max(cursor,data.sequence);
            if(type==='snapshot'){setJob(data);jobRef.current=data;setStreamError('');}
            if(data.access_revoked)throw Error('Board access changed. Reopen the board to continue.');
          });
          const authoritative=await api(`${base}/generations/${job.id}`,{signal:abort.signal});
          if(abort.signal.aborted)return;
          setJob(authoritative);jobRef.current=authoritative;
          if(!pendingJob(authoritative)){await refresh(false,abort.signal);break;}
        }catch(e){
          if(abort.signal.aborted)return;
          setStreamError('Progress connection interrupted. Reconnecting to saved job state…');
          // Reading state never creates or restarts a generation.
          try{const saved=await api(`${base}/generations/${job.id}`,{signal:abort.signal});if(abort.signal.aborted)return;setJob(saved);jobRef.current=saved;if(!pendingJob(saved)){await refresh(false,abort.signal);break;}}catch{/* retry the read after backoff */}
          await new Promise(resolve=>{const timer=setTimeout(resolve,2000);abort.signal.addEventListener('abort',()=>{clearTimeout(timer);resolve();},{once:true});});
        }
      }
    })();
    return()=>abort.abort();
  },[api,job?.id,!!pendingJob(job)]);
  useEffect(()=>{if(job&&!pendingJob(job)){const abort=new AbortController();refresh(false,abort.signal).catch(()=>{});return()=>abort.abort();}},[job?.id,job?.status]);
  useEffect(()=>{setReady(!!proposalReady);},[proposalReady]);
  useEffect(()=>{
    const partial=pendingJob(job)&&job.partial_preview?{partial:true,artifact:{id:job.artifact_id,versions:[],placement:null},version:{engine:'B',version:0,content:job.partial_preview}}:null;
    onProposal(partial||preview);
  },[preview,job?.partial_preview,job?.status,onProposal]);
  useEffect(()=>{if(!selection&&job?.status==='completed'&&job.version&&!handled.current.has(`${job.artifact_id}:${job.version}`)){
    handled.current.add(`${job.artifact_id}:${job.version}`);
    run(()=>openArtifact(job.artifact_id,job.version,true));
  }},[job?.id,job?.status]);
  useEffect(()=>{const node=feed.current;if(view==='ai'&&node&&node.scrollHeight-node.scrollTop-node.clientHeight<180)node.scrollTo({top:node.scrollHeight,behavior:'smooth'});},[chatJobs.length,messages.length,job?.status,preview,notice]);
  useEffect(()=>{if(preview&&ready)api(`${base}/artifacts/${preview.artifact.id}/versions/${preview.version.version}/render`,{method:'POST',...jsonBody({status:'ready'})}).catch(()=>{});},[preview?.artifact.id,preview?.version.version,ready]);



  async function run(action) {setBusy(true);setError('');try{await action();}catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}}
  async function submit(target, text=prompt.trim()||(attachmentState.ready.length?'Describe the attached sources.':files.length?'Analyze this image.':''), route=engine, selectedMode=mode) {
    if(submissionLock.current)return;
    submissionLock.current=true;
    try{return await run(async()=>{
    if(processingResources)throw Error('Attachments are still processing. Send again to wait for them.');
    if(!text&&!files.length&&!attachmentState.ready.length)throw Error('Add a message, retry an attachment, or choose a ready file before sending.');
    let draftIntelligence=intelligence;
    for(const entry of attachmentState.failed)draftIntelligence=withoutAttachmentSource(draftIntelligence,entry.resource,intelligenceResources);
    if(draftIntelligence.scope!=='selection'&&draftIntelligence.scope!=='board'&&!draftIntelligence.keys.length)draftIntelligence=DEFAULT_INTELLIGENCE;
    if(attachmentState.ready.length&&(draftIntelligence.scope==='selection'||draftIntelligence.scope!=='board'&&attachmentState.ready.some(f=>!draftIntelligence.keys.includes(resourceKey(f.resource)))))throw Error('Select the attached sources in Sources, or remove their attachment chips before sending.');
    let cid=conversationRef.current;
    if(cid==null){cid=await createChat();conversationRef.current=cid;setConversationId(cid);setChatJobs([]);}
    const requestedMode=target&&selectedMode==='auto'&&preview?.version?({A:'diagram',B:'ui'}[preview.version.engine]||selectedMode):selectedMode;
    draftIntelligence=resolveSourceAction(draftIntelligence,intelligenceResources,selection,requestedMode,text);
    const sourceSelection=selection||(target&&!preview?.artifact.placement&&preview?.version.selection?{context:preview.version.selection,request:{expected_revision:preview.version.selection.scene_revision,...(preview.version.selection.kind==='region'?{region:preview.version.selection.bounds}:{element_ids:preview.version.selection.element_ids}),...(preview.version.selection.resources||preview.version.selection.retrieval?{resources:preview.version.selection.retrieval?.source_refs||preview.version.selection.resources.map(r=>r.reference)}:{}),...(preview.version.selection.intelligence_request?{intelligence:preview.version.selection.intelligence_request}:{}),action:preview.version.selection.action,table_scopes:preview.version.selection.table_scopes||[]}}:null);
    if(sourceSelection&&!sourceSelection.capture&&sourceSelection.context.visual_attached)throw Error('Select this content again to regenerate with a fresh image.');
    let submittedFiles=files;
    const resourceImages=sourceSelection?.context.resources?.some(r=>r.reference.kind==='image');
    if(sourceSelection&&selectionVisual&&!resourceImages){if(!sourceSelection.capture)throw Error('Reselect this content to capture a fresh visual.');submittedFiles=[{id:'selection-image',file:await sourceSelection.capture()}];}
    let selectionRequest=sourceSelection?{...sourceSelection.request,visual:!!((sourceSelection.capture||resourceImages)&&selectionVisual)}:null;
    let intelligenceMode=null;
    if(draftIntelligence.scope!=='selection'){
      if(draftIntelligence.operation==='search')throw Error('Use Search passages locally. Search needs no Gemini call.');
      selectionRequest=intelligenceSelection(draftIntelligence,intelligenceResources,selection,revision,text);
      selectionRequest.visual=files.length>0;
      intelligenceMode=draftIntelligence.operation==='visualize'?'ui':requestedMode==='diagram'?'diagram':requestedMode==='ui'?'ui':requestedMode==='auto'?'auto':'chat';
      if(['diagram','ui'].includes(intelligenceMode))selectionRequest.action='modify';
    }
    const effectiveTarget=target;
    const signature=JSON.stringify([selectionRequest,text,route,target,cid,outputFormat,requestedMode,model?.selected,files.map(f=>f.id)]);
    if(pendingRequest.current?.signature!==signature)pendingRequest.current={signature,data:{...generationRequest(text,route,effectiveTarget),...(selectionRequest?{selection:selectionRequest}:{}),mode:intelligenceMode||(sourceSelection?(['modify','derive'].includes(sourceSelection.context.action)?(requestedMode==='chat'?'auto':requestedMode):'chat'):requestedMode),...(model?.selected?{model:model.selected}:{}),conversation_id:cid,...(outputFormat!=='auto'?{output_format:outputFormat}:{})}};
    let options={method:'POST',...jsonBody(pendingRequest.current.data)};
    if(submittedFiles.length){
      const body=new FormData();body.append('request',JSON.stringify(pendingRequest.current.data));submittedFiles.forEach(({file})=>body.append('attachments',file));
      const controller=new AbortController();uploadController.current=controller;setUploadProgress(0);
      options={method:'POST',body,signal:controller.signal,onUploadProgress:setUploadProgress};
    }
    try{
      const created=await api(`${base}/generations`,options);
      setJob(created);jobRef.current=created;pendingRequest.current=null;setNotice('');setPrompt('');setFiles([]);setResourceFiles(old=>old.filter(f=>['error','failed'].includes(f.status)));setIntelligence(draftIntelligence);setConfirmFailed(false);setSelection(null);setSelectionVisual(false);await refresh();
    }finally{uploadController.current=null;setUploadProgress(null);}
  });}finally{submissionLock.current=false;}
  }
  async function openArtifact(id,number,automatic=false) {
    const a=await api(`${base}/artifacts/${id}`);if(!automatic)setSelected(a);
    const version=a.versions.find(v=>v.version===number)||a.versions[0];
    if(automatic&&a.placement&&!a.placement.removed&&a.placement.version===version?.version)return;
    setReady(false);setPreview(version?{artifact:a,version}:null);setNotice('');
  }
  async function place(operation) {
    if(!current&&preview.version.selection?.action==='modify'&&!preview.version.selection?.resources?.length&&operation==='insert')operation='selection';
    await onPlace(preview.artifact,preview.version,operation);
    handled.current.add(proposalKey(preview));setPreview(null);setSelected(null);setReady(false);setNotice(operation==='remove'?'Removed from the canvas.':'Accepted to your canvas.');await refresh();
  }
  const active=pendingJob(job),current=preview?.artifact.placement;
  const conversation=[...chatJobs.filter(j=>j.id!==job?.id),...(job?[job]:[])].sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.id.localeCompare(b.id));
  function reject(){handled.current.add(proposalKey(preview));setPreview(null);setReady(false);setNotice('Proposal rejected. Your canvas is unchanged.');}
  const disabled=readOnly||busy||active||preferenceBusy||sendWaiting;

  const linkedIds=new Set(conversation.flatMap(j=>[j.user_message_id,j.assistant_message_id]).filter(Boolean));
  const linkedMessages=messages.filter(m=>!linkedIds.has(m.id));
  const resolvedIntelligence=resolveSourceAction(intelligence,intelligenceResources,selection,mode,prompt);
  const draftSourceSummary=sourceSummary(intelligence,intelligenceResources,selection);
  const sourceRefs=intelligenceReferences(intelligence,intelligenceResources,selection);
  const sourceActions=applicableActions(intelligenceResources.filter(r=>sourceRefs.some(ref=>resourceKey(ref)===resourceKey(r))));
  function changeIntelligence(value){
    const actionChanged=value.automatic===false&&(value.operation!==intelligence.operation||automaticSourceAction(intelligence));
    setIntelligence(value);pendingRequest.current=null;
    if(actionChanged&&value.operation!=='search')chooseMode(value.operation==='visualize'?'ui':'chat');
  }
  const selectedModel=model?.models.find(m=>m.id===model.selected);
  const imageUnsupported=selectedModel?.supports_images===false||(selectedModel?.input_modalities&&!selectedModel.input_modalities.some(m=>m.toLowerCase()==='image'));
  return <section className="canvas-ai" aria-label="Canvas AI assistant">
    <header className="generation-header">{settingsOpen?<><button aria-label="Back from settings" onClick={onBack}>←</button><div className="generation-heading"><h2>Settings</h2><small>Canvas AI</small></div></>:<><h2><span aria-hidden="true">✧</span> Canvas AI</h2><button className="primary new-canvas-chat" disabled={disabled||loading||processingResources} onClick={newChat}>＋ New chat</button></>}<div>{headerControls}{!settingsOpen&&<><button aria-label="Chat history" title="Chat history" aria-expanded={view==='conversations'} onClick={()=>onView(view==='conversations'?'ai':'conversations')}>☰</button><button aria-label="Generation history" title="Generation history" aria-expanded={historyOpen} onClick={()=>onView(historyOpen?'ai':'generations')}>↶</button><button aria-label="Canvas AI settings" title="Canvas AI settings" onClick={()=>onView('settings')}>⚙</button></>}{onClose&&<button aria-label="Close board sidebar" title="Close board sidebar" onClick={onClose}>✕</button>}</div></header>
    <div className="generation-secondary" hidden={!settingsOpen}>

      <section className="generation-settings" aria-label="Canvas AI settings">
        <CanvasAppearance />
        <details><summary>Generation options</summary><label>Structured format<select aria-label="Structured generation format" value={outputFormat} disabled={disabled} onChange={e=>{setOutputFormat(e.target.value);pendingRequest.current=null;}}><option value="auto">{openuiEnabled?'OpenUI preferred':'Legacy JSON (OpenUI disabled)'}</option><option value="openui-lang-v1" disabled={!openuiEnabled}>OpenUI Lang</option><option value="kumuta-json-v1">Legacy JSON</option></select></label></details>
        <details><summary>Model & usage</summary><p>Uses your shared Kumuta model and Gemini key. Your prompt, recent chat context, relevant artifact definitions and attached images are sent to the selected model.</p><a href={mainOrigin} target="_blank" rel="noopener noreferrer">Manage provider key, paid models & usage ↗</a>{job?.usage&&<p>{job.usage.estimated?'Estimated':'Provider reported'} · {job.usage.total_tokens} tokens</p>}{job?.usage_pending&&<p>Usage pending; submitted work may be billed.</p>}</details>
      </section>
    </div>
    <div className="generation-secondary" hidden={!historyOpen}><section aria-label="Saved generations"><h3>Generation history</h3>{loading?<p role="status">Loading saved jobs…</p>:!jobs.length?<p>No generations yet.</p>:<ul className="generation-history">{jobs.map(j=><li key={j.id}><strong>{j.prompt.slice(0,100)}</strong><small>{generationLabel(j.status)} · {new Date(j.created_at).toLocaleString()}</small><button disabled={busy} onClick={()=>run(async()=>{setJob(j);setPrompt(j.prompt);setEngine(j.engine==='T'?'auto':j.engine);if(j.version)await openArtifact(j.artifact_id,j.version);onView('ai');})}>{j.version?'Preview & versions':'View job'}</button></li>)}</ul>}{more&&<button disabled={busy} onClick={()=>run(()=>refresh(true))}>Load older generations</button>}<h3>Saved artifacts</h3>{artifacts.filter(a=>a.versions.length).map(a=><button className="generation-saved" data-artifact-id={a.id} key={a.id} disabled={busy} onClick={()=>run(async()=>{await openArtifact(a.id,a.placement?.version);onView('ai');})}>{a.versions[0].content.payload.title||'Diagram'}<small>{a.versions.length} version(s) · {a.placement&&!a.placement.removed?`Accepted v${a.placement.version}`:'Not on canvas'}</small></button>)}</section></div>
    <div className="generation-secondary" hidden={view!=='conversations'}><section aria-label="Board chats"><h3>Chats</h3><button className="chat-new-action" disabled={disabled||processingResources} onClick={newChat}>＋ New chat</button>
      {['Today','Older'].map(group=>{const today=new Date().toLocaleDateString();const rows=chats.filter(c=>(new Date(c.updated_at).toLocaleDateString()===today?'Today':'Older')===group);return rows.length>0&&<section className="canvas-chat-group" key={group}><h4>{group}</h4>{rows.map(c=><button className="canvas-chat-row" key={c.conversation_id} aria-current={conversationId===c.conversation_id?'page':undefined} disabled={busy||active||processingResources} onClick={()=>switchChat(c.conversation_id)}>{c.title}</button>)}</section>;})}
      {jobs.some(j=>j.conversation_id==null)&&<button className="canvas-chat-row" disabled={busy||active||processingResources} onClick={()=>switchChat(null)}>Earlier Canvas chats</button>}
      {!chats.length&&!jobs.length&&<p>No conversations yet.</p>}
    </section></div>
    <div className="generation-feed" ref={feed} hidden={view!=='ai'} onScroll={()=>{scrollTop.current=feed.current.scrollTop;}}>
        {chatMore&&<button disabled={busy} onClick={()=>run(olderMessages)}>Load earlier messages</button>}
        {!conversation.length&&!messages.length&&!preview&&<div className="generation-welcome"><span aria-hidden="true">✧</span><h3>What’s on your mind?</h3><p>Ask a question, explore an idea, or create something for your canvas.</p><div className="generation-ideas">{['Create a system architecture diagram','Build an illustrative project timeline','Make a quantity × price calculator'].map(idea=><button key={idea} disabled={disabled} onClick={()=>setPrompt(idea)}>{idea} ↗</button>)}</div></div>}
        {messagesMore&&<button disabled={busy} onClick={()=>run(olderLinkedMessages)}>Load earlier linked messages</button>}
        {linkedMessages.length>0&&<div className="generation-conversation linked-conversation" aria-label="Linked chat messages">{linkedMessages.map(m=><div key={m.id} className={m.role==='user'?'generation-user':'generation-reply'}><Markdown text={m.content} /></div>)}<a href={`${mainOrigin}/#/chat?conversation=${conversationId}`} target="_blank" rel="noopener noreferrer">Open in Kumuta AI ↗</a></div>}
        <div className="generation-conversation" role="log" aria-label="Canvas AI conversation" aria-live="polite">{conversation.map(j=><React.Fragment key={j.id}><div className="generation-user">{j.selection&&<small className="canvas-selection-provenance">Selection · {j.selection.element_ids.length} elements · {j.selection.widgets.length} widgets · v{j.selection.scene_revision}{j.selection.visual_attached?' · selected-region image sent':' · structured context'}</small>}{j.selection?.resources?.length>0&&<small>{j.selection.resources.length} resource sources</small>}{j.prompt}{j.attachments?.length>0&&<div className="canvas-sent-images">{j.attachments.map(a=><button type="button" key={a.id} onClick={()=>run(async()=>{const blob=await api(`/conversations/${j.conversation_id}/attachments/${j.user_message_id}/${a.id}`,{responseType:'blob'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=a.attachment_name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);})}>{a.attachment_name} ↧</button>)}</div>}</div><div className="generation-reply"><span aria-hidden="true">✧</span><div>{pendingJob(j)?(j.output_format==='openui-lang-v1'&&j.status==='generating'?'Generating with OpenUI…':generationLabel(j.status)):j.status==='completed'?<Markdown text={j.reply_text||'Your proposal is ready to review on the canvas.'} />:j.error||generationLabel(j.status)}{j.status==='completed'&&j.selection?.resources?.length>0&&<div className="resource-citations" aria-label="Resource sources">{j.selection.resources.map((r,i)=><button key={i} type="button" onClick={()=>onResource(r.reference)}>[{r.citation}] {r.label}</button>)}</div>}{j.id===job?.id&&active&&<><button disabled={busy} onClick={()=>run(async()=>{const saved=await api(`${base}/generations/${job.id}/cancel`,{method:'POST'});setJob(saved);await refresh();})}>Cancel generation</button>{streamError&&<p>{streamError}</p>}</>}{j.status==='completed'&&j.version&&j.id!==preview?.version.source_job_id&&<button disabled={busy||active} onClick={()=>run(()=>openArtifact(j.artifact_id,j.version))}>Review proposal</button>}{['failed','timed_out','cancelled'].includes(j.status)&&<button disabled={disabled} onClick={()=>{if(j.selection){setNotice('Select the content again and choose an AI action to retry with fresh context.');return;}pendingRequest.current=null;setPrompt(j.prompt);setEngine(j.engine==='T'?'auto':j.engine);setMode(j.engine==='T'?'chat':j.engine==='A'?'diagram':'ui');setOutputFormat(j.output_format||'auto');setSelected(j.artifact_id?{id:j.artifact_id}:null);setNotice('Ready to retry as a new request. This may use quota.');}}>Retry as new request</button>}{['failed','timed_out'].includes(j.status)&&<button disabled={busy||active} onClick={()=>onView('settings')}>Change model / settings</button>}{j.status==='completed'&&j.engine==='T'&&j.selection?.retrieval&&<button disabled={disabled} onClick={()=>run(async()=>{const artifact=await api(`${base}/intelligence/proposals`,{method:'POST',...jsonBody({request_key:crypto.randomUUID(),source_job_id:j.id,title:j.prompt.slice(0,200)||'Research report'})});setReady(false);setPreview({artifact,version:artifact.versions[0]});setSelected(null);setNotice('Report saved as a reviewable artifact. Accept to add it to the canvas.');await refresh();})}>Preview & save report</button>}{j.diagnostic&&<small>{j.diagnostic.category.replaceAll('_',' ')} · {j.diagnostic.stage}</small>}</div></div></React.Fragment>)}</div>
        {preview&&<section className="generation-preview" aria-label="Proposal approval"><h3>{preview.version.content.payload.title||'Diagram proposal'}</h3>{preview.version.selection&&<details className="canvas-selection-context"><summary>Affects {preview.version.selection.element_ids.length} selected elements</summary>{preview.version.selection.element_ids.join(', ')}<p>{preview.version.selection.resources?.length?'Accept adds a new artifact and preserves the source content.':'Accept replaces the complete selection. Unselected content is preserved.'}</p></details>}<p>{current&&!current.removed?`Proposed replacement for accepted v${current.version}.`:'Preview on your canvas.'}</p><div className="generation-actions"><button className="primary" disabled={!ready||disabled} onClick={()=>run(()=>place(current?'replace':'insert'))}>Accept to canvas</button><button disabled={busy} onClick={reject}>Reject</button><button disabled={disabled} onClick={()=>submit(preview.artifact.id,prompt||job?.prompt,preview.version.engine,preview.version.engine==='A'?'diagram':'ui')}>Regenerate</button></div>
          {preview.version.selection?.retrieval&&<details><summary>Sources and calculation scope</summary><p>{preview.version.selection.retrieval.coverage}</p>{preview.version.selection.resources?.map(r=><button key={r.citation} disabled={r.unavailable} onClick={()=>onResource(r.reference)}>[{r.citation}] {r.label}{r.unavailable?' · unavailable':''}</button>)}{preview.version.selection.verified_analysis?.results.map((r,i)=><small key={i}>{r.dataset.name} / {r.sheet}: {r.matched_rows} matching rows of {r.source_rows}; {r.warnings.join(' ')}</small>)}</details>}
          <details><summary>Versions & artifact actions</summary><label>Artifact version<select aria-label="Artifact version" value={preview.version.version} disabled={busy||active} onChange={e=>run(()=>openArtifact(preview.artifact.id,Number(e.target.value)))}>{preview.artifact.versions.map(v=><option key={v.version} value={v.version}>v{v.version} · {v.engine==='A'?'Diagram':'Interactive UI'}{current?.version===v.version?' · accepted':''}</option>)}</select></label>{current&&!current.removed&&<button disabled={disabled} onClick={()=>run(()=>place('remove'))}>Remove from scene</button>}<button disabled={!ready||disabled} onClick={()=>run(async()=>{const key=proposalKey(preview);if(!copyKeys.current.has(key))copyKeys.current.set(key,crypto.randomUUID());const copy=await api(`${base}/artifacts/${preview.artifact.id}/duplicate`,{method:'POST',...jsonBody({request_key:copyKeys.current.get(key),version:preview.version.version})});await onPlace(copy,copy.versions[0],'insert');copyKeys.current.delete(key);setPreview(null);setNotice('Duplicate accepted to your canvas.');await refresh();})}>Duplicate & insert</button></details>
        </section>}
        {notice&&<p role="status" className="generation-notice">{notice}</p>}
      {error&&view!=='ai'&&<div role="alert" className="generation-error"><p>{error}</p><button onClick={()=>run(()=>refresh())}>Refresh saved state</button></div>}
    </div>
    <form hidden={view!=='ai'} className={`generation-composer${dragging?' dragging':''}`} onSubmit={e=>{e.preventDefault();if(!disabled&&(prompt.trim()||files.length||resourceFiles.length)&&!(files.length&&imageUnsupported))requestSend();}}
      onPaste={e=>{const images=clipboardImages(e.clipboardData);if(images.length){e.preventDefault();addFiles(images);}}}
      onDragOver={e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();e.stopPropagation();if(!disabled)setDragging(true);}}}
      onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget))setDragging(false);}}
      onDrop={e=>{e.preventDefault();e.stopPropagation();setDragging(false);addFiles([...e.dataTransfer.files]);}}>
      {error&&<p role="alert" className="canvas-composer-error">{error}</p>}
      <div className="canvas-composer-context">
      {selection&&<small className="canvas-selection-summary" role="status">{selectionVisual?'Selected image will be sent':'Selected content only'}</small>}
      {selected&&<div className="generation-target"><span>Editing selected artifact</span><button type="button" aria-label="Start a new artifact" disabled={disabled} onClick={()=>{setSelected(null);setPreview(null);setNotice('');}}>＋ New artifact</button></div>}
      {files.length>0&&<div className="canvas-attachment-previews">{files.map(f=><AttachmentPreview key={f.id} file={f.file} disabled={disabled} onRemove={()=>{setFiles(old=>old.filter(x=>x.id!==f.id));pendingRequest.current=null;}} formatSize={size=>`${Math.ceil(size/1024)} KB`} />)}</div>}
      {resourceFiles.length>0&&<div className="canvas-resource-attachments" aria-label="Attached sources">{resourceFiles.map(f=><div className="canvas-resource-attachment" key={f.id}>
        <AttachmentPreview file={f.file} disabled={disabled} onRemove={()=>removeResourceFile(f)} formatSize={size=>`${Math.ceil(size/1024)} KiB · ${f.file.name.split('.').pop().toUpperCase()}`} />
        <small role="status">{f.status==='uploading'?`Uploading · ${f.progress}%`:f.status==='ready'?'Ready for RAG':f.status==='error'?'Processing failed':`${f.status} · not ready for RAG`}</small>
        {f.status==='uploading'&&<progress aria-label={`Upload ${f.file.name}`} value={f.progress} max="100"/>}
        {f.error&&<small role="alert">{f.error}</small>}
        {f.resource?.status==='ready'&&<button type="button" disabled={disabled} onClick={()=>onResource({schema_version:1,kind:f.resource.kind,source_id:f.resource.source_id,fingerprint:f.resource.fingerprint})}>Preview {f.file.name}</button>}
        {f.status==='error'&&<button type="button" disabled={disabled} onClick={()=>retryResourceFile(f)}>Retry {f.file.name}</button>}
      </div>)}</div>}
      {processingResources&&<small role="status">Attachments are processing. Send will wait until they finish.</small>}
      {sendWaiting&&<small role="status">Waiting to send… <button type="button" onClick={cancelSend}>Cancel send</button></small>}
      {confirmFailed&&<div className="canvas-composer-error" role="alert"><p>Some files could not be read. Retry or remove them, or send without the failed files.</p><button type="button" disabled={disabled||(!prompt.trim()&&!files.length&&!attachmentState.ready.length)} onClick={()=>{setConfirmFailed(false);submit(selected?.id);}}>Send without failed files</button><button type="button" onClick={()=>setConfirmFailed(false)}>Keep editing</button></div>}
      </div>
      <textarea aria-label="Describe what you want" id="canvas-ai-prompt" value={prompt} onChange={e=>{setPrompt(e.target.value);pendingRequest.current=null;}} maxLength={4000} minLength={1} required={!files.length&&!resourceFiles.length} ref={promptInput} rows={1} placeholder="Ask Canvas AI..." disabled={disabled} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(!disabled&&(prompt.trim()||files.length||resourceFiles.length))e.currentTarget.form.requestSubmit();}}} />
      {draftSourceSummary&&<div className="canvas-draft-routing" aria-label="Active sources and action">
        <button type="button" className="canvas-active-sources" title={`${intelligence.scope==='board'?'All ready board sources · ':''}${draftSourceSummary}`} aria-label={`Active sources: ${draftSourceSummary}`} disabled={disabled} onClick={()=>sourceTrigger.current?.click()}><Scan size={13} aria-hidden="true"/><span>{intelligence.scope==='board'?'Board · ':''}{draftSourceSummary}</span></button>
        {intelligence.scope!=='selection'&&<label className="canvas-inline-action"><span className="visually-hidden">Source action</span><select aria-label="Source action" value={automaticSourceAction(intelligence)?'auto':intelligence.operation} disabled={disabled} onChange={e=>changeIntelligence(e.target.value==='auto'?{...intelligence,automatic:true,operation:'ask'}:{...intelligence,automatic:false,operation:e.target.value,fullDocument:false,confirmFull:false,analyses:[]})}>
          <option value="auto">Auto · {SOURCE_ACTION_LABELS[resolvedIntelligence.operation]}</option>{sourceActions.map(action=><option key={action} value={action}>{SOURCE_ACTION_LABELS[action]}</option>)}
        </select></label>}
      </div>}
      {dragging&&<small role="status">Drop supported files here</small>}
      {uploadProgress!==null&&<div role="status" className="canvas-upload-progress">Uploading images · {uploadProgress}%<progress value={uploadProgress} max="100" /></div>}
      {files.length>0&&imageUnsupported&&<p role="alert">This model does not support images. Remove them or choose another model.</p>}
      {modelError&&<div className="canvas-composer-error" role="alert">{modelError}<a href={mainOrigin} target="_blank" rel="noopener noreferrer">Set up your Gemini key / model in Kumuta AI</a><button type="button" disabled={disabled} onClick={()=>loadModels(true)}>Retry model list</button></div>}
      <input type="file" ref={fileInput} hidden multiple accept={CANVAS_ACCEPT} aria-label="Choose attachments" onChange={e=>{addFiles([...e.target.files]);e.target.value='';}} />
      <div className="generation-composer-footer">
        <button type="button" className="canvas-attach-button" aria-label="Attach files" title={`Attach ${CANVAS_TYPES}`} disabled={disabled||!!selection} onClick={()=>fileInput.current.click()}><Plus size={19} aria-hidden="true"/></button>
        <CanvasModelPicker catalogue={model} disabled={disabled} onSelect={chooseModel} onRefresh={()=>loadModels(true)} />
        <CanvasComposerPopover className="canvas-source-picker" triggerRef={sourceTrigger} menuClassName="canvas-source-menu" label="Sources / Selection" disabled={view!=='ai'} title={`Sources / Selection · ${selection?'Canvas selection':intelligence.scope}${intelligence.keys.length?` · ${intelligence.keys.length} sources`:''}`} trigger={<><Scan size={16} aria-hidden="true"/><span className="visually-hidden">Sources / Selection</span>{(selection||intelligence.scope!=='selection')&&<i className="canvas-source-active" aria-hidden="true"/>}</>}>
      <CanvasIntelligence active={view==='ai'} api={api} board={board} revision={revision} selection={selection} prompt={prompt} value={resolvedIntelligence} onChange={changeIntelligence} resources={intelligenceResources} onResources={setIntelligenceResources} disabled={disabled} onResource={onResource} onProposal={artifact=>{setReady(false);setPreview({artifact,version:artifact.versions[0]});setSelected(null);setNotice('Verified local proposal. Review, then Accept or Reject.');refresh().catch(e=>setError(e.message));}} />
      {selection&&<div className="canvas-selection-context" aria-label="Selection context"><strong>{selection.context.element_ids.length} elements · {selection.context.widgets.length} widgets · {selection.context.resources?.length||0} resources · {selection.context.action}</strong><span>Only selected content is included. Send to ask AI.</span>{selection.context.resources?.length>0&&<small>{selection.context.resources.map(r=>r.label).join(' · ')}</small>}{selection.context.visual_required&&<label><input type="checkbox" checked={selectionVisual} disabled={disabled||imageUnsupported} onChange={e=>setSelectionVisual(e.target.checked)} />{selection.context.resources?.some(r=>r.reference.kind==='image')?'Send selected resource images to Gemini (2 MiB maximum)':'Send a cropped image of selected native content to Gemini (2 MiB maximum)'}</label>}{selectionVisual&&<small>Visual context will be sent with your message.</small>}<button type="button" disabled={disabled} onClick={()=>{setSelection(null);setSelectionVisual(false);pendingRequest.current=null;}}>Clear selection context</button></div>}
        </CanvasComposerPopover>
        <label className="canvas-mode-picker"><span className="visually-hidden">Generation mode</span><select aria-label="Generation mode" value={mode} disabled={disabled} onChange={e=>chooseMode(e.target.value)} title="Choose how Canvas AI responds"><option value="auto">Auto</option><option value="chat">Text</option><option value="ui">Interactive UI</option><option value="diagram">Diagram</option></select></label>
        <button className="primary generation-send" aria-label="Send message" title="Send message" disabled={disabled||(!prompt.trim()&&!files.length&&!resourceFiles.length)||((files.length>0||selectionVisual)&&imageUnsupported)}>{active?'…':<ArrowUp size={18} aria-hidden="true"/>}</button>
      </div>
    </form>
  </section>;
}
