import React, { useEffect, useRef, useState } from 'react';
import { jsonBody } from './api';
import Modal, { Empty, ErrorNotice } from './Modal';
import { EditDialog, Text } from './ModeUI';
import { allPages } from './workspaceData';
import './dataAnalysis.css';
import DataAnalyze from './DataAnalyze';
import DataTable from './DataTable';
import DataReports from './DataReports';


export default function DataAnalysis({ api, project, registerGuard, initialView = 'Datasets', initialDatasetId }) {
  const base = `/projects/${project.id}/data`;
  const [saveRequest, setSaveRequest] = useState(null);
  const guards = useRef([]);
  const canLeave = React.useCallback(()=>guards.current.every(fn=>fn()),[]);
  useEffect(()=>registerGuard?.(canLeave),[registerGuard,canLeave]);
  const guard = React.useCallback(fn=>{guards.current.push(fn);return()=>{guards.current=guards.current.filter(g=>g!==fn);};},[]);
  function navigate(next) { if(canLeave()) setView(next); }
  const [view, setView] = useState(initialView), [rows, setRows] = useState(null), [overview, setOverview] = useState(null);
  const [selected, setSelected] = useState(initialDatasetId||null), [sheet, setSheet] = useState(''), [preview, setPreview] = useState(null), [offset, setOffset] = useState(0);
  const [previewVersion,setPreviewVersion]=useState(0);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [progress, setProgress] = useState(null), [rename, setRename] = useState(null), [deleting, setDeleting] = useState(null);
  const input = useRef(), generation = useRef(0), writing = useRef(false);
  const dataset = rows?.find(r => r.id === selected);
  async function refresh() {
    const n = ++generation.current;
    try { const [items, summary] = await Promise.all([allPages(api, base + '/datasets'), api(base + '/overview')]);
      if (n === generation.current) { setRows(items); setOverview(summary); setError(''); setSelected(id => items.some(r=>r.id===id) ? id : null); }
    } catch (e) { if(n===generation.current) setError(e.message); }
  }
  useEffect(() => { refresh(); return () => { generation.current++; }; }, [api, base]);
  useEffect(() => {
    if (!rows?.some(r => ['queued','processing'].includes(r.status))) return;
    const timer = setInterval(refresh, 1500); return () => clearInterval(timer);
  }, [rows]);
  useEffect(() => {
    setPreview(null); if (view !== 'Datasets' || !dataset || dataset.status !== 'ready') return;
    let alive = true;
    api(`${base}/datasets/${dataset.id}/preview?limit=25&offset=${offset}${sheet ? `&sheet=${encodeURIComponent(sheet)}` : ''}`)
      .then(r => { if(alive) { setPreview(r); setError(''); } }).catch(e=> { if(alive) setError(e.message); });
    return () => { alive=false; };
  }, [api, base, selected, dataset?.revision, sheet, offset, previewVersion, view]);
  function choose(row) { setSelected(row.id); setSheet(''); setOffset(0); navigate('Datasets'); }
  async function upload(file) {
    if (!file || writing.current) return;
    if (!/\.(csv|xlsx)$/i.test(file.name)) { setError('Choose a CSV or XLSX file.'); return; }
    writing.current=true; setBusy(true); setError(''); setProgress(0);
    try { const form = new FormData(); form.append('file', file);
      const row = await api(base + '/datasets', {method:'POST',body:form,onUploadProgress:setProgress});
      await refresh(); choose(row);
    } catch(e) { setError(e.message); } finally { writing.current=false; setBusy(false); setProgress(null); if(input.current) input.current.value=''; }
  }
  async function mutate(path, method, data) {
    if(writing.current) throw new Error('Wait for the current operation.');
    writing.current=true; setBusy(true); setError('');
    try { const result=await api(path,{method,...jsonBody(data)}); await refresh(); return result; }
    catch(e) { setError(e.message); throw e; } finally { writing.current=false; setBusy(false); }
  }
  return <section className="data-workspace" aria-label="Data Analysis workspace">
    <div className="data-heading"><div><span className="ws-eyebrow">PROJECT / DATA INTELLIGENCE</span><h2>Data Analysis</h2><p>Select data, ask a question, review the calculation and save your result.</p></div><div className="data-actions"><button className="secondary" disabled={busy} onClick={()=>{setPreviewVersion(v=>v+1);refresh();}}>Refresh data</button><button className="primary compact" disabled={busy || project.archived} onClick={()=>input.current.click()}>+ Upload Dataset</button></div>
      <input ref={input} type="file" accept=".csv,.xlsx" aria-label="Upload dataset file" className="data-file-input" onChange={e=>upload(e.target.files[0])}/></div>
    <ol className="data-flow" aria-label="Data workflow">{['Upload','Explore','Analyze','Visualize','Save'].map((s,i)=><li key={s}><span>{i+1}</span>{s}{i<4 && <b aria-hidden="true">›</b>}</li>)}</ol>
    <nav className="data-tabs" aria-label="Data Analysis views">{['Datasets','Analyze','Reports','Overview'].map(v=><button key={v} aria-current={view===v?'page':undefined} className={view===v?'active':''} onClick={()=>navigate(v)}>{v}</button>)}</nav>
    <ErrorNotice error={error} retry={()=>{setPreviewVersion(v=>v+1);refresh();}}/>{progress!==null && <p role="status">Uploading {progress}% · Processing starts locally after upload.</p>}
    {!rows && !error && <p role="status">Loading project datasets…</p>}
    {view==='Overview' && overview && <>
      <div className="data-stats">{[['datasets','Datasets'],['rows','Dataset rows'],['columns','Columns across sheets'],['reports','Saved reports']].map(([key,label])=><div key={key}><span>{label}</span><strong>{overview[key].toLocaleString()}</strong></div>)}</div>
      {!rows?.length ? <Empty title="Your data, a new perspective"><p>Upload a CSV or Excel workbook to explore real data, ask questions and save reports.</p><button className="primary compact" disabled={busy||project.archived} onClick={()=>input.current.click()}>Upload your first dataset</button></Empty> : <div className="data-overview-grid"><section className="data-card"><h3>Recently uploaded</h3>{overview.recent_datasets.map(r=><button className="data-recent" key={r.id} onClick={()=>choose(r)}><span className={`data-format ${r.format}`}>{r.format.toUpperCase()}</span><span><b>{r.name}</b><small>{r.row_count.toLocaleString()} rows · {r.column_count} columns · {r.status}</small></span><span>↗</span></button>)}</section><section className="data-card"><h3>Available insights</h3><p>Schema and missing values are computed from your source files.</p>{overview.recent_datasets.filter(r=>r.status==='ready').map(r=><div key={r.id}><b>{r.name}</b>{r.sheets.map(s=><p key={s.name}>{s.name}: {s.columns.reduce((n,c)=>n+c.missing,0)} missing cells · {s.columns.filter(c=>['integer','decimal'].includes(c.type)).length} numeric columns</p>)}</div>)}</section></div>}
      {!!overview.recent_reports.length && <section className="data-card data-recent-reports"><h3>Recent reports</h3>{overview.recent_reports.map(r=><button key={r.id} className="data-recent" onClick={()=>navigate('Reports')}><span>▤</span><span><b>{r.name}</b><small>{r.widgets.length} widgets · {r.updated_at.slice(0,10)}</small></span><span>↗</span></button>)}</section>}
    </>}
    {view==='Datasets' && rows && <div className="data-datasets"><aside className="data-card"><h3>Datasets <small>{rows.length}</small></h3>{rows.map(r=><button key={r.id} className={`data-recent ${selected===r.id?'selected':''}`} onClick={()=>choose(r)}><span className={`data-format ${r.format}`}>{r.format.toUpperCase()}</span><span><b>{r.name}</b><small>{r.row_count.toLocaleString()} rows · {r.status}</small></span></button>)}{!rows.length && <p>Upload a dataset to begin.</p>}</aside>
      <section className="data-card data-detail">{!dataset ? <Empty title="Explore a dataset">Upload a CSV or Excel workbook, or select a project dataset to preview real rows and ask a question.</Empty> : <><div className="data-heading"><div><h3>{dataset.name}</h3><p>{dataset.filename} · {(dataset.size/1024).toFixed(1)} KB · {dataset.status}</p></div><div className="data-actions"><button className="secondary" disabled={busy||project.archived} onClick={()=>setRename(dataset)}>Rename dataset</button><button className="secondary danger" disabled={busy} onClick={()=>setDeleting(dataset)}>Delete dataset</button></div></div>
      {dataset.error && <div role="alert"><p>{dataset.error}</p><button className="secondary" disabled={busy||dataset.attempts>=3||project.archived} onClick={()=>mutate(`${base}/datasets/${dataset.id}/retry`,'POST',{revision:dataset.revision}).catch(()=>{})}>Retry processing</button></div>}
      {dataset.status==='ready' && <><label className="mode-field">Worksheet<select aria-label="Dataset worksheet" value={sheet||dataset.sheets[0]?.name} onChange={e=>{setSheet(e.target.value);setOffset(0);}}>{dataset.sheets.map(s=><option key={s.name}>{s.name}</option>)}</select></label>
        {!preview ? <p role="status">Loading preview…</p> : <><p>{preview.row_count.toLocaleString()} rows · {preview.column_count} columns · Local processing, zero AI calls</p>{preview.warnings.map(w=><p className="data-warning" key={w}>{w}</p>)}<DataTable columns={preview.columns.map(c=>c.name)} rows={preview.items}/><div className="data-actions"><button className="secondary" disabled={!offset} onClick={()=>setOffset(n=>Math.max(0,n-25))}>Previous rows</button><span>Rows {preview.items.length?offset+1:0}–{offset+preview.items.length}</span><button className="secondary" disabled={!preview.has_more} onClick={()=>setOffset(n=>n+25)}>Next rows</button></div><button className="primary compact" onClick={()=>navigate('Analyze')}>Analyze this dataset →</button><h4>Column information & statistics</h4><DataTable caption="Column statistics" columns={['Column','Type','Missing','Distinct','Minimum','Maximum','Average']} rows={preview.columns.map(c=>[c.name,c.type+(c.mixed?' (mixed)':''),c.missing,c.distinct,c.min??null,c.max??null,c.average??null])}/></>}
      </>}{['queued','processing'].includes(dataset.status) && <p role="status">Processing safely on your server… This view updates automatically.</p>}</> }</section></div>}
    {view==='Analyze' && rows && <DataAnalyze api={api} base={base} datasets={rows} initialId={selected} registerGuard={guard} onSave={r=>{setSaveRequest(r);setView('Reports');}} />}
    {view==='Reports' && rows && <DataReports api={api} base={base} datasets={rows} archived={project.archived} registerGuard={guard} saveRequest={saveRequest} onConsumed={()=>setSaveRequest(null)} onChanged={refresh} />}
    {rename && <EditDialog title="Rename dataset" initial={{name:rename.name}} registerGuard={guard} onClose={()=>setRename(null)} onSave={d=>mutate(`${base}/datasets/${rename.id}`,'PATCH',{...d,revision:rename.revision})}>{(d,c)=><Text label="Dataset name" value={d.name} onChange={v=>c('name',v)} required maxLength={200}/>}</EditDialog>}
    {deleting && <Modal title="Delete dataset" onClose={()=>setDeleting(null)} busy={busy}><div className="mode-form"><p>Delete “{deleting.name}” and its source file? Reports using it will show an unavailable dataset.</p><div className="data-actions"><button className="secondary" disabled={busy} onClick={()=>setDeleting(null)}>Cancel</button><button className="secondary danger" disabled={busy} onClick={()=>mutate(`${base}/datasets/${deleting.id}`,'DELETE',{revision:deleting.revision,confirmation:'DELETE'}).then(()=>setDeleting(null)).catch(()=>{})}>Confirm delete dataset</button></div></div></Modal>}
  </section>;
}
