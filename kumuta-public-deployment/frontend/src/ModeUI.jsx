import React, { useEffect, useRef, useState } from 'react';
import Modal, { ErrorNotice } from './Modal';
import { jsonBody } from './api';
import { allPages } from './workspaceData';

export function useModeData(api, paths) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const generation = useRef(0), writing = useRef(false), latest = useRef(paths); latest.current = paths;
  async function refresh() {
    const id = ++generation.current;
    try { const rows = await Promise.all(Object.entries(latest.current).map(async ([key, path]) => [key, await allPages(api, path)]));
      if (id === generation.current) { setData(Object.fromEntries(rows)); setError(''); }
    } catch (e) { if (id === generation.current) setError(e.message); throw e; }
  }
  useEffect(() => { setData(null); refresh().catch(() => {}); return () => { generation.current++; }; }, [api, JSON.stringify(paths)]);
  async function mutate(path, method, body) {
    if (writing.current) throw new Error('Wait for the current save to finish.');
    writing.current = true; setBusy(true); setError('');
    try {
      const row = await api(path, { method, ...jsonBody(body) });
      try { await refresh(); } catch (e) { setError(`Saved, but could not refresh: ${e.message}`); }
      return row;
    } catch (e) { setError(e.message); throw e; }
    finally { writing.current = false; setBusy(false); }
  }
  return { data, error, busy, refresh, mutate };
}

export function ModeStatus({ store }) {
  return <><ErrorNotice error={store.error} retry={() => store.refresh().catch(() => {})} />{!store.data && !store.error && <p role="status">Loading…</p>}</>;
}
export function Field({ label, children }) { return <label className="mode-field"><span>{label}</span>{children}</label>; }
export function Text({ label, value, onChange, multiline = false, ...props }) {
  const Tag = multiline ? 'textarea' : 'input';
  return <Field label={label}><Tag value={value ?? ''} onChange={e => onChange(e.target.value)} {...props} /></Field>;
}
export function Progress({ value }) { return <div className="mode-progress"><progress max="100" value={value} aria-label="Completion" /><span>{value}%</span></div>; }
export function Origin({ value }) { return <small className="mode-origin">{value === 'ai' ? 'AI-generated · review before using' : 'User-authored'}</small>; }
export function EditDialog({ title, initial, onSave, onClose, children, registerGuard }) {
  const [draft, setDraft] = useState(initial), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  const change = (key, value) => setDraft(d => ({ ...d, [key]: value }));
  const close = () => { if (!busy && (!dirty || window.confirm('Discard unsaved changes?'))) onClose(); };
  useEffect(() => registerGuard?.(() => !busy && (!dirty || window.confirm('Discard unsaved changes?'))), [registerGuard, dirty, busy]);
  useEffect(() => { const before = e => { if (dirty || busy) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before); }, [dirty, busy]);
  return <Modal title={title} onClose={close} busy={busy}><form className="mode-form" onSubmit={async e => {
    e.preventDefault(); if (busy) return; setBusy(true); setError('');
    try { await onSave(draft); onClose(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }}><ErrorNotice error={error} />{children(draft, change)}<div className="mode-actions"><button type="button" className="secondary" disabled={busy} onClick={close}>Cancel</button><button className="primary compact" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div></form></Modal>;
}
export function Milestones({ values, onChange }) {
  return <fieldset><legend>Milestones</legend>{values.map((x, i) => <div className="mode-milestone" key={i}>
    <input aria-label={`Milestone ${i + 1}`} required maxLength="200" value={x.title} onChange={e => onChange(values.map((m, n) => n === i ? { ...m, title: e.target.value } : m))} />
    <input aria-label={`Milestone ${i + 1} target date`} type="date" value={x.target_date || ''} onChange={e => onChange(values.map((m, n) => n === i ? { ...m, target_date: e.target.value || null } : m))} />
    <label><input type="checkbox" checked={x.completed} onChange={e => onChange(values.map((m, n) => n === i ? { ...m, completed: e.target.checked } : m))} />Done</label>
    <button type="button" className="secondary" aria-label={`Remove milestone ${i + 1}`} onClick={() => onChange(values.filter((_, n) => n !== i))}>×</button>
  </div>)}<button className="secondary" type="button" onClick={() => onChange([...values, { title: '', completed: false, target_date: null }])}>+ Milestone</button></fieldset>;
}
export function Links({ label, rows, ids, onChange }) {
  return <Field label={label}><select multiple value={ids.map(String)} onChange={e => onChange([...e.target.selectedOptions].map(x => Number(x.value)))}>{rows.map(x => <option value={x.id} key={x.id}>{x.title}</option>)}</select><small>Use Ctrl or Command to select multiple items.</small></Field>;
}
