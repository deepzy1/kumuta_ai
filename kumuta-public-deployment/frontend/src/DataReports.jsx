import React, { useEffect, useRef, useState } from 'react';
import { jsonBody } from './api';
import Modal, { ErrorNotice, Empty } from './Modal';
import { EditDialog, Field, Text } from './ModeUI';
import { allPages } from './workspaceData';
import { AnalysisControls, AnalysisResult } from './DataAnalyze';
import { defaultSpec, moveWidget } from './dataAnalysis';

function WidgetEditor({initial,datasets,api,base,onSave,onClose,registerGuard}){
 const ready=datasets.filter(r=>r.status==='ready');
 const [schema,setSchema]=useState(null),[error,setError]=useState(''),[identity,setIdentity]=useState({id:initial.dataset_id,sheet:initial.spec.sheet});
 useEffect(()=>{let alive=true;setSchema(null);setError('');if(!identity.id)return;api(`${base}/datasets/${identity.id}/schema${identity.sheet?`?sheet=${encodeURIComponent(identity.sheet)}`:''}`).then(r=>{if(alive)setSchema(r);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[identity.id,identity.sheet,api,base]);
 return <EditDialog title="Configure visualization" initial={initial} registerGuard={registerGuard} onClose={onClose} onSave={d=>{if(!schema)throw new Error('Select an available dataset.');onSave(d);}}>{(d,c)=>{
  const row=ready.find(r=>r.id===d.dataset_id);
  return <><ErrorNotice error={error}/><Text label="Widget title" value={d.title} onChange={v=>c('title',v)} maxLength={120} required/>
   <Field label="Widget dataset"><select aria-label="Widget dataset" value={d.dataset_id||''} onChange={e=>{const id=Number(e.target.value);c('dataset_id',id);c('source_sha256',null);c('spec',defaultSpec());setIdentity({id,sheet:null});}}><option value="" disabled>Choose a dataset</option>{ready.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
   <Field label="Widget worksheet"><select aria-label="Widget worksheet" value={d.spec.sheet||row?.sheets[0]?.name||''} onChange={e=>{c('spec',{...defaultSpec(),sheet:e.target.value});setIdentity({id:d.dataset_id,sheet:e.target.value});}}>{row?.sheets.map(s=><option key={s.name}>{s.name}</option>)}</select></Field>
   <AnalysisControls schema={schema} spec={d.spec} onChange={s=>c('spec',s)} disabled={!schema}/>
  </>;
 }}</EditDialog>;
}

function ReportEditor({report,api,base,datasets,archived,registerGuard,onSaved,onClose}){
 const initial={name:report.name,description:report.description,widgets:report.widgets};
 const [draft,setDraft]=useState(initial),[baseline,setBaseline]=useState(JSON.stringify(initial)),[revision,setRevision]=useState(report.revision),[output,setOutput]=useState(null),[widget,setWidget]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const writing=useRef(false),dirty=JSON.stringify(draft)!==baseline;
 const canLeave=()=>!busy&&(!dirty||window.confirm('Discard unsaved report changes?'));
 useEffect(()=>registerGuard?.(canLeave),[registerGuard,dirty,busy]);
 useEffect(()=>{const before=e=>{if(dirty||busy){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before);},[dirty,busy]);
 function change(key,value){setDraft(d=>({...d,[key]:value}));setOutput(null);}
 async function run(){if(writing.current)return;writing.current=true;setBusy(true);setError('');setOutput(null);try{setOutput(await api(`${base}/reports/${report.id}/run`,{method:'POST'}));}catch(e){setError(e.message);}finally{writing.current=false;setBusy(false);}}
 useEffect(()=>{run();},[report.id]);
 useEffect(()=>{let closed=[];const before=()=>{closed=[...document.querySelectorAll('.data-print-report details:not([open])')];closed.forEach(d=>d.open=true);};const after=()=>{closed.forEach(d=>d.open=false);closed=[];};window.addEventListener('beforeprint',before);window.addEventListener('afterprint',after);return()=>{window.removeEventListener('beforeprint',before);window.removeEventListener('afterprint',after);};},[]);
 async function save(e){e.preventDefault();if(writing.current)return;writing.current=true;setBusy(true);setError('');setOutput(null);try{const row=await api(`${base}/reports/${report.id}`,{method:'PUT',...jsonBody({...draft,revision})});setDraft({name:row.name,description:row.description,widgets:row.widgets});setBaseline(JSON.stringify({name:row.name,description:row.description,widgets:row.widgets}));setRevision(row.revision);await onSaved(row);setOutput(await api(`${base}/reports/${report.id}/run`,{method:'POST'}));}catch(e){setError(e.message);}finally{writing.current=false;setBusy(false);}}
 async function download(format){if(writing.current)return;writing.current=true;setBusy(true);setError('');try{const blob=await api(`${base}/reports/${report.id}/export?format=${format}`,{responseType:'blob'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`kumuta-report-${report.id}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){setError(e.message);setOutput(null);}finally{writing.current=false;setBusy(false);}}
 return <section className="data-report-editor" aria-label="Report editor"><div className="data-actions data-no-print"><button className="secondary" disabled={busy} onClick={()=>{if(canLeave())onClose();}}>← All reports</button><button className="secondary" disabled={busy||dirty} onClick={run}>Refresh report</button><button className="secondary" disabled={busy||dirty} onClick={()=>download('csv')}>Export CSV</button><button className="secondary" disabled={busy||dirty} onClick={()=>download('json')}>Export JSON</button><button className="secondary" disabled={busy||dirty||!output} onClick={()=>window.print()}>Print report</button></div><ErrorNotice error={error}/>
  <form onSubmit={save} className="data-card data-no-print"><Text label="Report name" value={draft.name} onChange={v=>change('name',v)} required maxLength={200} disabled={busy||archived}/><Text label="Report description" value={draft.description} onChange={v=>change('description',v)} multiline maxLength={1000} disabled={busy||archived}/>
   <div className="data-actions"><button type="button" className="secondary" disabled={busy||archived||draft.widgets.length>=8||!datasets.some(r=>r.status==='ready')} onClick={()=>setWidget({key:crypto.randomUUID(),title:'New visualization',dataset_id:datasets.find(r=>r.status==='ready').id,source_sha256:null,spec:defaultSpec()})}>+ Add visualization</button><button className="primary compact" disabled={busy||archived||!dirty}>Save report changes</button><small role="status">{busy?'Working…':dirty?'Unsaved changes · Save to refresh/export':'All changes saved'}</small></div>
   {draft.widgets.map((w,i)=><div className="data-widget-config" key={w.key}><span><b>{w.title}</b><small>{datasets.find(d=>d.id===w.dataset_id)?.name||'Dataset unavailable'} · {w.spec.chart}</small></span><div className="data-actions"><button type="button" className="secondary" disabled={busy||archived||i===0} aria-label={`Move ${w.title} up`} onClick={()=>change('widgets',moveWidget(draft.widgets,i,-1))}>↑</button><button type="button" className="secondary" disabled={busy||archived||i===draft.widgets.length-1} aria-label={`Move ${w.title} down`} onClick={()=>change('widgets',moveWidget(draft.widgets,i,1))}>↓</button><button type="button" className="secondary" disabled={busy||archived} onClick={()=>setWidget(w)}>Configure {w.title}</button><button type="button" className="secondary danger" disabled={busy||archived} aria-label={`Remove ${w.title}`} onClick={()=>{if(window.confirm(`Remove “${w.title}” from this report draft?`))change('widgets',draft.widgets.filter(v=>v.key!==w.key));}}>Remove</button></div></div>)}
  </form>
  {dirty && <p className="data-warning data-no-print">Save the current configuration to calculate its results. Refresh and exports use saved configurations.</p>}
  {output && <div className="data-print-report"><header><span className="ws-eyebrow">KUMUTA AI / DATA REPORT</span><h2>{output.report.name}</h2><p>{output.report.description}</p><small>Refreshed {new Date(output.generated_at).toLocaleString()} · Local calculations</small></header><div className="data-report-widgets">{output.widgets.map(w=><AnalysisResult key={w.key} title={w.title} result={w.result}/>)}</div>{!output.widgets.length&&<Empty title="Build your first visualization">Add a widget, choose columns and save your report.</Empty>}</div>}
  {widget && <WidgetEditor initial={widget} datasets={datasets} api={api} base={base} registerGuard={registerGuard} onClose={()=>setWidget(null)} onSave={w=>{change('widgets',draft.widgets.some(v=>v.key===w.key)?draft.widgets.map(v=>v.key===w.key?w:v):[...draft.widgets,w]);}}/>}
 </section>;
}

export default function DataReports({api,base,datasets,archived,registerGuard,saveRequest,onConsumed,onChanged}){
 const [reports,setReports]=useState(null),[opened,setOpened]=useState(null),[creating,setCreating]=useState(false),[deleting,setDeleting]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const generation=useRef(0);
 async function refresh(){const id=++generation.current;try{const rows=await allPages(api,base+'/reports');if(id===generation.current){setReports(rows);setError('');}}catch(e){if(id===generation.current)setError(e.message);}}
 useEffect(()=>{refresh();return()=>{generation.current++;};},[api,base]);
 async function saved(){await refresh();await onChanged();}
 async function create(d){const row=await api(base+'/reports',{method:'POST',...jsonBody(d)});await saved();setOpened(row);}
 return <><ErrorNotice error={error} retry={refresh}/>{opened?<ReportEditor key={opened.id} report={opened} api={api} base={base} datasets={datasets} archived={archived} registerGuard={registerGuard} onSaved={saved} onClose={()=>setOpened(null)}/>:<>
  <div className="data-heading"><div><h3>Saved reports</h3><p>Reusable dashboards powered by your stored datasets.</p></div><button className="primary compact" disabled={busy||archived} onClick={()=>setCreating(true)}>+ Create report</button></div>
  {!reports&&!error&&<p role="status">Loading reports…</p>}{reports?.length?<div className="data-report-list">{reports.map(r=><article key={r.id} className="data-card"><h3>{r.name}</h3><p>{r.description||'A private project report'}</p><small>{r.widgets.length} widgets · Updated {new Date(r.updated_at).toLocaleDateString()}</small><div className="data-actions"><button className="secondary" onClick={()=>setOpened(r)}>Open {r.name}</button><button className="secondary danger" onClick={()=>setDeleting(r)}>Delete {r.name}</button></div></article>)}</div>:reports&&<Empty title="From a question to a saved report">Create a report here or save a result from Analyze.</Empty>}
 </>}
 {creating&&<EditDialog title="Create report" initial={{name:'',description:'',widgets:[]}} registerGuard={registerGuard} onClose={()=>setCreating(false)} onSave={create}>{(d,c)=><><Text label="New report name" value={d.name} onChange={v=>c('name',v)} required maxLength={200}/><Text label="Description" value={d.description} onChange={v=>c('description',v)} multiline maxLength={1000}/></>}</EditDialog>}
 {saveRequest&&reports&&<SaveAnalysis result={saveRequest} reports={reports} api={api} base={base} registerGuard={registerGuard} onClose={onConsumed} onSaved={async row=>{await saved();setOpened(row);onConsumed();}}/>}
 {deleting&&<Modal title="Delete report" onClose={()=>setDeleting(null)} busy={busy}><div className="mode-form"><p>Permanently delete “{deleting.name}”? Your datasets stay available.</p><div className="data-actions"><button className="secondary" disabled={busy} onClick={()=>setDeleting(null)}>Cancel</button><button className="secondary danger" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await api(`${base}/reports/${deleting.id}`,{method:'DELETE',...jsonBody({revision:deleting.revision,confirmation:'DELETE'})});setDeleting(null);await saved();}catch(e){setError(e.message);}finally{setBusy(false);}}}>Confirm delete report</button></div></div></Modal>}
 </>;
}

function SaveAnalysis({result,reports,api,base,registerGuard,onClose,onSaved}){
 return <EditDialog title="Save analysis to report" initial={{report_id:'',name:'My data report',description:'',title:'Analysis visualization'}} registerGuard={registerGuard} onClose={onClose} onSave={async d=>{
  const widget={key:crypto.randomUUID(),title:d.title,dataset_id:result.dataset.id,source_sha256:result.dataset.sha256,spec:result.spec};
  let row;
  if(d.report_id){const original=await api(`${base}/reports/${d.report_id}`);row=await api(`${base}/reports/${d.report_id}`,{method:'PUT',...jsonBody({name:original.name,description:original.description,widgets:[...original.widgets,widget],revision:original.revision})});}
  else row=await api(base+'/reports',{method:'POST',...jsonBody({name:d.name,description:d.description,widgets:[widget]})});
  await onSaved(row);
 }}>{(d,c)=><><Field label="Save into report"><select value={d.report_id} onChange={e=>c('report_id',e.target.value)}><option value="">Create a new report</option>{reports.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>{!d.report_id&&<Text label="New report name" value={d.name} onChange={v=>c('name',v)} required maxLength={200}/>}{!d.report_id&&<Text label="Report description" multiline maxLength={1000} value={d.description} onChange={v=>c('description',v)}/>}<Text label="Visualization title" value={d.title} onChange={v=>c('title',v)} required maxLength={120}/></>}</EditDialog>;
}
