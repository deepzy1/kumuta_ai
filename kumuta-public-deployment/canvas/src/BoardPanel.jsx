import React, { useEffect, useRef, useState } from 'react';
import CanvasResources from '@kumuta/CanvasResources.jsx';
import {SidebarButtons,SidebarResize} from '@kumuta/CanvasSidebarControls.jsx';
import CanvasAI from '@kumuta/CanvasAI.jsx';
import { ErrorNotice } from '@kumuta/Modal.jsx';
const mainOrigin=import.meta.env.VITE_KUMUTA_APP_URL || `${location.protocol}//${location.hostname}:5173`;
export default function BoardPanel({ sidebar, onDismiss, api, board, readOnly, tab, setTab, revision, onRestore, onPlace, session, onProposal, proposalReady, selectionIntent, onAddResource, onAskResource, onOpenResource, resourcePreview }) {
  const panelRef=useRef(null),previous=useRef('ai');
  const navigate=next=>{if(next==='settings')previous.current=tab;setTab(next);};
  const assistantView=['ai','conversations','settings','generations'].includes(tab);
  useEffect(()=>()=>{
    if(panelRef.current?.contains(document.activeElement))document.querySelector('[aria-label="Open board sidebar"]')?.focus();
  },[]);
  const [rows,setRows]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[more,setMore]=useState(false),[attempt,setAttempt]=useState(0);
  async function fetchRows(append=false,signal) {
    setBusy(true);setError('');
    try {
      const result=await api(`/boards/${board.id}/${tab==='history'?`revisions?limit=25&offset=${append?rows.length:0}`:tab}`,{signal});
      if(signal?.aborted)return;
      setRows(old=>append?[...old,...result.items]:result.items);setMore(!!result.has_more);
    } catch(e) {if(!signal?.aborted)setError(e.message);} finally {if(!signal?.aborted)setBusy(false);}
  }
  useEffect(()=>{setRows([]);setMore(false);if(tab!=='history')return;const abort=new AbortController();fetchRows(false,abort.signal);return()=>abort.abort();},[api,board.id,tab,revision,attempt]);
  const content = <aside ref={panelRef} style={{'--canvas-sidebar-width':`${sidebar.width}px`}} className={`board-panel canvas-resizable-panel ${assistantView?'has-ai':''}`} aria-label="Board sidebar" onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onDismiss();document.querySelector('[aria-label="Open board sidebar"]')?.focus();}}}><SidebarResize sidebar={sidebar}/><header><strong>Canvas AI</strong><SidebarButtons sidebar={sidebar}/><button aria-label="Close board sidebar" onClick={onDismiss}>✕</button></header>{tab!=='settings'&&<nav aria-label="Board sections">{[['ai','AI'],['conversations','Chats'],['resources','Resources'],['history','History']].map(([key,name])=><button key={key} className={tab===key?'current':''} aria-current={tab===key?'page':undefined} onClick={()=>navigate(key)}>{name}</button>)}</nav>}
    <div className={`panel-content ${assistantView?'ai-panel-content':''}`}><div className="mounted-canvas-ai" hidden={!assistantView}>{board.role==='viewer'?<p>Viewer access · AI and personal conversations are unavailable.</p>:<CanvasAI headerControls={<SidebarButtons sidebar={sidebar}/>} onResource={onOpenResource} selectionIntent={selectionIntent} view={tab} onView={navigate} onBack={()=>setTab(previous.current)} onClose={()=>{onDismiss();document.querySelector('[aria-label="Open board sidebar"]')?.focus();}} session={session} onProposal={onProposal} proposalReady={proposalReady} api={api} board={board} readOnly={readOnly} onPlace={onPlace} revision={revision} />}</div>{tab==='resources'&&(board.role!=='owner'?<p>Source unavailable · Original files, previews, citations and fresh RAG evidence remain private to the owner.</p>:<CanvasResources api={api} board={board} readOnly={readOnly} onAdd={onAddResource} onAsk={onAskResource} previewRequest={resourcePreview}/>)}{!assistantView&&tab!=='resources'&&<><h2>{tab==='history'?'Revision history':tab==='resources'?'Linked resources':'Board conversations'}</h2><ErrorNotice error={error} retry={()=>setAttempt(n=>n+1)} />{busy&&!rows.length?<p role="status">Loading…</p>:!rows.length&&!error?<p>{tab==='history'?'Your first save will start this board’s history.':tab==='resources'?'No documents are explicitly linked to this board.':'No conversations are linked to this board.'}</p>:<ul className="panel-list">{rows.map(row=><li key={row.revision || row.document_id || row.conversation_id}>{tab==='history'?<><div><strong>Revision {row.revision}</strong>{row.revision===revision&&<span className="current-badge">Current</span>}</div><small>{new Date(row.created_at).toLocaleString()}{row.restored_from?` · Restored from v${row.restored_from}`:''}</small><button disabled={readOnly||row.revision===revision} onClick={()=>onRestore(row.revision)}>Restore revision {row.revision}</button></>:tab==='resources'?<><strong>{row.filename}</strong><small>{row.status} · Document #{row.document_id}</small><p>Managed by the existing Kumuta document service.</p></>:<><strong>Conversation #{row.conversation_id}</strong><a href={`${mainOrigin}/#/chat?conversation=${row.conversation_id}`} target="_blank" rel="noopener noreferrer">Open in Kumuta AI ↗</a></>}</li>)}</ul>}{more&&<button disabled={busy} onClick={()=>fetchRows(true)}>{busy?'Loading…':'Load older revisions'}</button>}<small className="panel-scope">Only this board’s authorized links are shown.</small></>}
    </div></aside>;
  return content;
}
