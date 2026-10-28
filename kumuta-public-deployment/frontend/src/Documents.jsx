import React, { useEffect, useRef, useState } from 'react';
import { jsonBody } from './api';
import Modal, { Empty, ErrorNotice } from './Modal';
import { DOCUMENT_ACCEPT, validateDocuments } from './documents';

export async function downloadDocument(api, row, open = false, page = null) {
  const blob = await api(`/documents/${row.id}/file`, { responseType: 'blob' });
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url + (open && page && row.mime === 'application/pdf' ? `#page=${page}` : '');
  if (open && row.mime === 'application/pdf') { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
  else link.download = row.filename;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function DocumentPreview({ api, source, onClose }) {
  const [row, setRow] = useState(null), [chunks, setChunks] = useState([]), [more, setMore] = useState(false);
  const [page, setPage] = useState(source.page || ''), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0), [focusCitation, setFocusCitation] = useState(!!source.chunk_id);
  const id = source.document_id || source.id;
  useEffect(() => {
    let alive = true; setLoading(true); setError('');
    api(`/documents/${id}/chunks?${focusCitation ? `chunk_id=${source.chunk_id}` : page ? `page=${page}` : ''}`)
      .then(result => { if (alive) { setRow(result.document); setChunks(result.items); setMore(result.has_more); } })
      .catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [api, id, page, focusCitation, reload]);
  async function loadMore() {
    setLoading(true);
    try { const result = await api(`/documents/${id}/chunks?offset=${chunks.length}${page ? `&page=${page}` : ''}`); setChunks(previous => [...previous, ...result.items]); setMore(result.has_more); }
    catch (e) { setError(e.message); } finally { setLoading(false); }
  }
  return <Modal title="Document preview" onClose={onClose} wide><div className="doc-preview"><ErrorNotice error={error} retry={() => setReload(n => n + 1)} />
    {row && <><h3>{row.filename}</h3><div className="doc-preview-toolbar"><button className="secondary" onClick={() => downloadDocument(api, row, true, page).catch(e => setError(e.message))}>{row.mime === 'application/pdf' ? 'Open original PDF' : 'Download original'}</button>
      {row.pages > 0 && <label>Page<input aria-label="Preview page" type="number" min={1} max={row.pages} value={page} placeholder="All" onChange={e => { setFocusCitation(false); setPage(e.target.value); }} /></label>}
      {focusCitation && <button className="secondary" onClick={() => setFocusCitation(false)}>Show surrounding page</button>}</div>
      {row.warning && <p className="ws-info">{row.warning}</p>}{row.status !== 'ready' && <p role="status">{row.error || `Document is ${row.status}.`}</p>}
      <div className="doc-passages">{chunks.map(chunk => <section key={chunk.chunk_id}><small>[{chunk.citation}] · {chunk.page ? `Page ${chunk.page}` : chunk.section || 'Text'}</small><pre>{chunk.text}</pre></section>)}</div>
      {more && <button className="secondary" disabled={loading} onClick={loadMore}>More passages</button>}</>}
    {loading && <p role="status">Loading document preview…</p>}
  </div></Modal>;
}

export function DocumentSources({ sources, onOpen }) {
  if (!sources?.length) return null;
  return <section className="doc-citations" aria-label="Document sources"><strong>Document sources</strong><div>{sources.map(source => <button key={source.citation} onClick={() => onOpen(source)}>
    <span>[{source.citation}] {source.filename}</span><small>{source.page ? `Page ${source.page}` : source.section || 'Text passage'} ↗</small>
  </button>)}</div></section>;
}

export default function DocumentsPanel({ api, projectId, conversationId, archived = false, initialSelected = [], onAsk, onChat, onTask, onStudy, registerGuard, onBusy }) {
  const [rows, setRows] = useState([]), [q, setQ] = useState(''), [status, setStatus] = useState(''), [offset, setOffset] = useState(0), [more, setMore] = useState(false);
  const [hits, setHits] = useState([]), [selected, setSelected] = useState(initialSelected), [preview, setPreview] = useState(null);
  const [error, setError] = useState(''), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [progress, setProgress] = useState(null);
  const [dragging, setDragging] = useState(false), [reload, setReload] = useState(0), [mode, setMode] = useState('search');
  const [fileType, setFileType] = useState(''), [layout, setLayout] = useState('list');
  const picker = useRef(null), uploadController = useRef(null);
  const scope = projectId ? { project_id: projectId } : { conversation_id: conversationId };
  const query = new URLSearchParams(scope).toString();
  useEffect(() => { setOffset(0); }, [q, status, fileType]);
  useEffect(() => registerGuard?.(() => !busy), [registerGuard, busy]);
  useEffect(() => { onBusy?.(busy); }, [onBusy, busy]);
  useEffect(() => () => uploadController.current?.abort(), []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    Promise.all([api(`/documents?${query}&q=${encodeURIComponent(q)}&offset=${offset}${status ? `&status=${status}` : ''}${fileType ? `&file_type=${fileType}` : ''}`, { signal: controller.signal }),
      q.trim() ? api(`/documents/search?${query}&q=${encodeURIComponent(q)}`, { signal: controller.signal }) : Promise.resolve({ items: [] })])
      .then(([list, search]) => { setRows(list.items); setMore(list.has_more); setHits(search.items); })
      .catch(e => { if (e.name !== 'AbortError') setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, query, q, offset, status, fileType, reload]);
  useEffect(() => {
    if (!rows.some(r => ['queued', 'processing'].includes(r.status))) return;
    const timer = setTimeout(() => setReload(n => n + 1), 2000); return () => clearTimeout(timer);
  }, [rows, reload]);
  async function upload(files) {
    if (busy || archived) return;
    const invalid = validateDocuments(files); if (invalid) { setError(invalid); return; }
    setBusy(true); setError('');
    const controller = new AbortController(); uploadController.current = controller;
    const failures = [];
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i], body = new FormData(); body.append('file', file);
        for (const [key, value] of Object.entries(scope)) body.append(key, value);
        setProgress({ name: file.name, percent: 0, index: i + 1, total: files.length });
        try { await api('/documents', { method: 'POST', body, signal: controller.signal, onUploadProgress: percent => setProgress({ name: file.name, percent, index: i+1, total: files.length }) }); }
        catch (e) { if (e.name === 'AbortError') throw e; failures.push(`${file.name}: ${e.message}`); }
      }
    } catch (e) { if (e.name !== 'AbortError') failures.push(e.message); }
    finally { uploadController.current = null; setBusy(false); setProgress(null); setReload(n => n + 1); if (failures.length) setError(failures.join(' ')); }
  }
  async function mutation(action) {
    if (busy) return; setBusy(true); setError('');
    try { await action(); setReload(n => n + 1); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="documents-panel"><div className="ws-page-title"><div><h2>Documents</h2><p>{projectId ? 'Upload and manage files for this project.' : 'Files for this conversation, plus its project references.'}</p></div><button className="primary compact" disabled={busy || archived} onClick={() => picker.current.click()}>Upload documents</button></div>
    <input ref={picker} type="file" accept={DOCUMENT_ACCEPT} multiple hidden aria-label="Choose documents" onChange={e => { const files = [...e.target.files]; e.target.value = ''; upload(files); }} />
    <div className={`doc-dropzone ${dragging ? 'dragging' : ''}`} onDragOver={e => { if ([...e.dataTransfer.types].includes('Files')) { e.preventDefault(); e.stopPropagation(); setDragging(true); } }} onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); e.stopPropagation(); setDragging(false); upload([...e.dataTransfer.files]); }}>
      <strong>Drop your reference files here</strong><span>PDF, DOCX, TXT, Markdown · 8 MB each · 5 files / 20 MB per upload batch</span><small>Processing and search stay local. Images remain available through chat attachments.</small>
    </div>
    {progress && <div className="doc-upload-progress" role="status"><span>Uploading {progress.index}/{progress.total}: {progress.name} · {progress.percent}%</span><progress value={progress.percent} max="100" /></div>}
    <ErrorNotice error={error} retry={() => setReload(n => n + 1)} />
    <div className="ws-toolbar"><input type="search" aria-label="Search documents" placeholder="Search filenames and document text…" value={q} onChange={e => setQ(e.target.value)} /><select aria-label="Document status" value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option>{['queued', 'processing', 'ready', 'error'].map(value => <option key={value}>{value}</option>)}</select><select aria-label="Document file type" value={fileType} onChange={e => setFileType(e.target.value)}><option value="">All file types</option><option value="pdf">PDF</option><option value="docx">Word</option><option value="text">Text / Markdown</option></select><div className="ws-segment" aria-label="Document view"><button aria-pressed={layout === 'list'} onClick={() => setLayout('list')}>List</button><button aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')}>Grid</button></div><button className="secondary" disabled={busy} onClick={() => setReload(n => n + 1)}>Refresh documents</button></div>
    <div className="doc-selection"><span>{selected.length} selected</span><select aria-label="Document AI action" value={mode} onChange={e => setMode(e.target.value)}><option value="search">Ask a question</option><option value="summarize">Summarize complete documents</option><option value="compare">Compare complete documents</option></select>
      <button className="primary compact" disabled={busy || !selected.length || (mode !== 'search' && selected.length > 4) || (mode === 'compare' && selected.length < 2)} onClick={() => onAsk?.(selected, mode)}>Ask AI about selected</button><button className="secondary" disabled={!selected.length || busy} onClick={() => setSelected([])}>Clear selection</button></div>
    {mode !== 'search' && <p className="ws-info">Complete summaries/comparisons process every extracted passage. Long documents may use multiple AI requests; you’ll confirm before sending. Select up to 4 files.</p>}
    {loading ? <p role="status">Loading documents…</p> : <div className={`document-list ${layout}`}>{rows.map(row => <article className="document-card" key={row.id}><div className="document-card-main"><input type="checkbox" aria-label={`Select ${row.filename}`} disabled={row.status !== 'ready' || busy || (!selected.includes(row.id) && selected.length >= 20)} checked={selected.includes(row.id)} onChange={e => setSelected(ids => e.target.checked ? [...ids, row.id] : ids.filter(id => id !== row.id))} />
      <div><button className="doc-filename" onClick={() => setPreview(row)}>{row.filename}</button><small>{Math.ceil(row.size/1024)} KB{row.pages ? ` · ${row.pages} pages` : ''} · {row.chunk_count} passages</small></div><span className={`doc-status ${row.status}`}>{row.status === 'error' ? 'Needs attention' : row.status}</span></div>
      <p className="document-origin">{row.conversation_id && onChat ? <button className="ws-text-button" onClick={() => onChat(row.conversation_id)}>Open originating conversation</button> : row.conversation_id ? 'From a conversation' : 'Project library'} · {new Date(row.created_at).toLocaleDateString()}</p>
      {onTask && row.task_refs?.map(task => <button className="ws-text-button" key={task.id} onClick={() => onTask(task.id)}>Task: {task.title} →</button>)}
      {row.error && <p className="doc-error">{row.error}</p>}<div className="document-actions">{onStudy&&row.status==='ready'&&<button className="secondary" disabled={archived} onClick={()=>onStudy(row.id)}>Create study course</button>}<button className="secondary" onClick={() => setPreview(row)}>Preview</button><button className="secondary" onClick={() => downloadDocument(api, row).catch(e => setError(e.message))}>Download</button>
        {row.status === 'error' && <button className="secondary" disabled={busy || archived || row.attempts >= 5} onClick={() => mutation(() => api(`/documents/${row.id}/retry`, { method: 'POST', ...jsonBody({ revision: row.revision }) }))}>Retry processing</button>}
        <button className="secondary danger" disabled={busy} onClick={() => { if (window.confirm(`Delete “${row.filename}” and its searchable passages?`)) mutation(async () => { await api(`/documents/${row.id}`, { method: 'DELETE', ...jsonBody({ revision: row.revision, confirmation: 'DELETE' }) }); setSelected(ids => ids.filter(id => id !== row.id)); }); }}>Delete document</button></div>
    </article>)}{!rows.length && <Empty title={q ? 'No matching filenames' : 'Bring your sources together'}>Upload a document, then select it to ask a grounded question.</Empty>}</div>}
    {!!hits.length && <section className="doc-search-results"><h3>Matching passages</h3>{hits.map(hit => <button key={hit.chunk_id} onClick={() => setPreview(hit)}><strong>{hit.filename} · {hit.page ? `Page ${hit.page}` : hit.section}</strong><p>{hit.text.slice(0, 350)}</p></button>)}</section>}
    <div className="ws-form-actions"><button className="secondary" disabled={!offset || busy} onClick={() => setOffset(Math.max(0, offset-50))}>Previous</button><button className="secondary" disabled={!more || busy} onClick={() => setOffset(offset+50)}>Next</button></div>
    {preview && <DocumentPreview api={api} source={preview} onClose={() => setPreview(null)} />}
  </div>;
}
