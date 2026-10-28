import React, { useEffect, useRef, useState } from 'react';
import { allPages } from './workspaceData';
import { DOCUMENT_ACCEPT, validateDocuments } from './documents';
import { DocumentPreview } from './Documents';
import { ErrorNotice } from './Modal';

export default function TaskDocuments({ api, project, ids, onChange, disabled, onBusy }) {
  const [rows, setRows] = useState([]), [error, setError] = useState(''), [busy, setBusy] = useState(false), [reload, setReload] = useState(0), [preview, setPreview] = useState(null);
  const picker = useRef(null);
  useEffect(() => { onBusy?.(busy); }, [busy, onBusy]);
  useEffect(() => {
    let alive = true;
    allPages(api, `/documents?project_id=${project.id}`).then(rows => { if (alive) setRows(rows); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [api, project.id, reload]);
  async function upload(files) {
    const invalid = validateDocuments(files); if (invalid) { setError(invalid); return; }
    if (busy || disabled) return; setBusy(true); setError('');
    const added = [];
    try { for (const file of files) { const body = new FormData(); body.append('file', file); body.append('project_id', project.id); const row = await api('/documents', { method: 'POST', body }); added.push(row.id); } }
    catch (e) { setError(e.message); }
    finally { if (added.length) onChange([...new Set([...ids, ...added])].slice(0, 20)); setBusy(false); setReload(n => n + 1); }
  }
  return <section className="task-documents"><h3>Document attachments</h3><p className="muted">Use project files without storing another copy. Save the task to keep your selection.</p><ErrorNotice error={error} />
    <input type="file" ref={picker} hidden multiple accept={DOCUMENT_ACCEPT} aria-label="Upload task documents" onChange={e => { upload([...e.target.files]); e.target.value = ''; }} />
    <button type="button" className="secondary" disabled={disabled || busy || ids.length >= 20} onClick={() => picker.current.click()}>{busy ? 'Uploading…' : 'Upload to project library'}</button>
    {rows.map(row => <div className="task-document-row" key={row.id}><label><input type="checkbox" disabled={disabled || busy || (!ids.includes(row.id) && ids.length >= 20)} checked={ids.includes(row.id)} onChange={e => onChange(e.target.checked ? [...ids, row.id] : ids.filter(id => id !== row.id))} />{row.filename}</label><button type="button" className="ws-text-button" onClick={() => setPreview(row)}>Preview</button></div>)}
    {!rows.length && <p className="muted">Upload a document or add one in the project library.</p>}
    {preview && <DocumentPreview api={api} source={preview} onClose={() => setPreview(null)} />}
  </section>;
}
