import React, { useEffect, useRef, useState } from 'react';
import Modal, { ErrorNotice } from './Modal';
import { Field, Text } from './ModeUI';
import { allPages } from './workspaceData';
import { jsonBody } from './api';

const sources = [['topic','From a topic','Describe what you want to learn.'],['document','From a document','Upload a PDF or reuse a project file.'],['url','From a URL','Use an English Wikipedia article.'],['manual','Create manually','Write your own course. No AI needed.']];
export default function StudyCreate({ api, project, registerGuard, onManual, onSaved, onClose, initialDocumentId }) {
  const [source,setSource]=useState(initialDocumentId?'document':'topic'),[topic,setTopic]=useState(''),[objective,setObjective]=useState(''),[difficulty,setDifficulty]=useState('beginner');
  const [documents,setDocuments]=useState([]),[did,setDid]=useState(initialDocumentId?String(initialDocumentId):''),[url,setUrl]=useState(''),[consent,setConsent]=useState(false),[draft,setDraft]=useState(null),[reference,setReference]=useState(null);
  const [busy,setBusy]=useState(false),[status,setStatus]=useState(''),[error,setError]=useState('');
  const lock=useRef(false),file=useRef();
  const dirty=!!(topic||objective||draft);
  const canLeave=()=>!lock.current&&(!dirty||window.confirm('Discard this unsaved course draft?'));
  useEffect(()=>registerGuard?.(canLeave),[registerGuard,dirty]);
  useEffect(()=>{const before=e=>{if(dirty||lock.current){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before);},[dirty]);
  useEffect(()=>{
    if(source!=='document')return;
    let alive=true,timer;
    const load=async()=>{try{const rows=await allPages(api,`/documents?project_id=${project.id}`);if(alive){setDocuments(rows);if(rows.some(r=>['queued','processing'].includes(r.status)))timer=setTimeout(load,1500);}}catch(e){if(alive)setError(e.message);}};
    load();return()=>{alive=false;clearTimeout(timer);};
  },[api,project.id,source,did]);
  async function upload(selected){
    if(!selected||lock.current)return;
    lock.current=true;setBusy(true);setError('');setStatus('Uploading source document…');
    try{const body=new FormData();body.append('file',selected);body.append('project_id',project.id);const doc=await api('/documents',{method:'POST',body});setDocuments(rows=>[doc,...rows.filter(r=>r.id!==doc.id)]);setDid(String(doc.id));setStatus('Source saved in Project Documents. Wait for processing before generating.');}
    catch(e){setError(e.message);}finally{lock.current=false;setBusy(false);}
  }
  async function generate(e){
    e.preventDefault();if(lock.current)return;lock.current=true;setBusy(true);setError('');setStatus('Creating your course outline… This can take up to two minutes.');
    try{const r=await api(`/projects/${project.id}/study/draft`,{method:'POST',...jsonBody({topic,objective,difficulty,source,document_id:Number(did)||null,url,confirm_source:consent})});setDraft(r.outline);setReference(r.source);setStatus(`Draft ready · AI-generated with ${r.model}. Review before saving.`);}
    catch(e){setError(e.message);setStatus('No course was saved. You can retry or create manually.');}finally{lock.current=false;setBusy(false);}
  }
  async function save(e){
    e.preventDefault();if(lock.current)return;lock.current=true;setBusy(true);setError('');setStatus('Saving your reviewed course…');
    try{const row=await api(`/projects/${project.id}/study/outline`,{method:'POST',...jsonBody({outline:draft,document_id:reference?.document_id||null,url:reference?.url||''})});setStatus('Course saved.');await onSaved(row);}
    catch(e){setError(e.message);setStatus('Your draft is retained.');}finally{lock.current=false;setBusy(false);}
  }
  const updateChapter=(i,change)=>setDraft(d=>({...d,chapters:d.chapters.map((c,n)=>n===i?{...c,...change}:c)}));
  const ready=documents.find(r=>r.id===Number(did))?.status==='ready';
  return <Modal title={draft?'Review course outline':'Create course'} wide busy={busy} onClose={()=>{if(canLeave())onClose();}}><div className="mode-form study-create"><ErrorNotice error={error}/><p role="status" aria-live="polite">{status}</p>
    {!draft?<><div className="study-source-options" role="group" aria-label="Course source">{sources.map(([id,label,help])=><button key={id} className={source===id?'selected':''} aria-pressed={source===id} disabled={busy} onClick={()=>{if(id==='manual'){onManual();return;}setSource(id);setConsent(false);setError('');}}><strong>{label}</strong><span>{help}</span></button>)}</div>
      <form className="mode-form" onSubmit={generate}><Text label="Topic" required maxLength={200} value={topic} onChange={setTopic} disabled={busy}/><Text label="Learning objective" multiline maxLength={4000} value={objective} onChange={setObjective} disabled={busy}/><Field label="Difficulty"><select disabled={busy} value={difficulty} onChange={e=>setDifficulty(e.target.value)}>{['beginner','intermediate','advanced'].map(v=><option key={v}>{v}</option>)}</select></Field>
      {source==='document'&&<><Field label="Course source document"><select disabled={busy} required value={did} onChange={e=>setDid(e.target.value)}><option value="">Choose a project document</option>{documents.map(d=><option key={d.id} value={d.id}>{d.filename} · {d.status}</option>)}</select></Field><input hidden ref={file} type="file" accept=".pdf,.docx,.txt,.md" aria-label="Upload course source" onChange={e=>upload(e.target.files[0])}/><button type="button" className="secondary" disabled={busy} onClick={()=>file.current.click()}>Upload source document</button></>}
      {source==='url'&&<Text label="Wikipedia article URL" type="url" required value={url} onChange={setUrl} placeholder="https://en.wikipedia.org/wiki/Photosynthesis" disabled={busy}/>}
      {source!=='topic'&&<label className="study-consent"><input type="checkbox" required checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/>Send up to 24,000 source characters to my selected model to draft this course.</label>}
      <p className="muted">Uses your selected model, API key and free/paid settings. One generation, recorded in Usage. Nothing is saved until you review the outline.</p><div className="mode-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>{if(canLeave())onClose();}}>Cancel</button><button className="primary compact" disabled={busy||(source==='document'&&!ready)}>{busy?'Generating…':'Generate outline'}</button></div></form></>:
      <form className="mode-form" onSubmit={save}><p className="mode-origin">AI-generated · Review titles, content, practice questions and source coverage.</p>{reference?.title&&<p>Source: {reference.title}. {reference.warning}</p>}
        <Text label="Course title" required maxLength={200} value={draft.title} onChange={title=>setDraft(d=>({...d,title}))} disabled={busy}/><Text label="Course description" multiline value={draft.description} onChange={description=>setDraft(d=>({...d,description}))} disabled={busy}/><Text label="Course objectives" multiline value={draft.objectives} onChange={objectives=>setDraft(d=>({...d,objectives}))} disabled={busy}/>
        {draft.chapters.map((chapter,i)=><fieldset key={i} disabled={busy}><legend>Chapter {i+1}</legend><Text label={`Chapter ${i+1} title`} required maxLength={200} value={chapter.title} onChange={title=>updateChapter(i,{title})}/>{chapter.lessons.map((lesson,j)=><div className="study-outline-lesson" key={j}><Text label={`Lesson ${i+1}.${j+1} title`} required maxLength={200} value={lesson.title} onChange={title=>updateChapter(i,{lessons:chapter.lessons.map((l,n)=>n===j?{...l,title}:l)})}/><details><summary>Review lesson content & practice</summary><Text label={`Lesson ${i+1}.${j+1} content`} multiline maxLength={8000} rows={8} value={lesson.content} onChange={content=>updateChapter(i,{lessons:chapter.lessons.map((l,n)=>n===j?{...l,content}:l)})}/></details></div>)}</fieldset>)}
        <div className="mode-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>setDraft(null)}>Back to source</button><button className="primary compact" disabled={busy}>{busy?'Saving…':'Save course & start learning'}</button></div></form>}
  </div></Modal>;
}
