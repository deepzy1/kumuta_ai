import React, { useEffect, useState } from 'react';
import { jsonBody } from './api';
import Modal, { Empty, ErrorNotice } from './Modal';

export function memoryScope(scope, projectId, conversationId) {
  return { scope, ...(scope === 'project' ? { project_id: projectId } : {}), ...(scope === 'conversation' ? { conversation_id: conversationId } : {}) };
}

export function RememberDialog({ api, projectId, conversationId, content, onClose }) {
  const [scope, setScope] = useState(conversationId ? 'conversation' : projectId ? 'project' : 'global');
  const [text, setText] = useState(content.slice(0, 4000)), [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(null);
  async function save(e) {
    e.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try { const row = await api('/memories', { method: 'POST', ...jsonBody({ ...memoryScope(scope, projectId, conversationId), content: text, consent }) }); setSaved(row); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function forget() {
    setBusy(true); setError('');
    try { await api(`/memories/${saved.id}`, { method: 'DELETE', ...jsonBody({ revision: saved.revision }) }); onClose(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Modal title="Remember this" onClose={onClose} busy={busy}><form className="ws-form memory-form" onSubmit={save}>
    <ErrorNotice error={error} />
    {saved ? <><p role="status">{saved.duplicate ? 'This memory was already saved.' : 'Memory saved privately. Enable memory in Saved memories to use it in answers.'}</p>
      <div className="ws-form-actions"><button type="button" className="secondary danger" disabled={busy} onClick={forget}>Forget this</button><button type="button" className="primary compact" onClick={onClose}>Done</button></div></>
      : <><label>Save to<select value={scope} onChange={e => setScope(e.target.value)}><option value="global">Global · all your chats</option>{projectId && <option value="project">This project</option>}{conversationId && <option value="conversation">This conversation</option>}</select></label>
      <label>Memory text<textarea aria-label="Memory text" value={text} maxLength={4000} rows={6} onChange={e => setText(e.target.value)} required /></label>
      <p className="muted">Only save facts and preferences you want reused. Avoid passwords, keys and sensitive personal information. Nothing is saved automatically.</p>
      <label className="memory-check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />I approve saving this memory privately.</label>
      <div className="ws-form-actions"><button className="primary compact" disabled={busy || !consent || !text.trim()}>{busy ? 'Saving…' : 'Save memory'}</button></div></>}
  </form></Modal>;
}

export default function MemoryPanel({ api, projectId, conversationId }) {
  const [scope, setScope] = useState(projectId ? 'project' : 'global'), [q, setQ] = useState('');
  const [rows, setRows] = useState([]), [more, setMore] = useState(false), [offset, setOffset] = useState(0);
  const [settings, setSettings] = useState(null), [master, setMaster] = useState(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0), [remember, setRemember] = useState(false), [editing, setEditing] = useState(null), [draft, setDraft] = useState('');
  const data = memoryScope(scope, projectId, conversationId);
  const query = new URLSearchParams(data).toString();
  const settingsQuery = scope === 'all' ? 'scope=global' : query;
  useEffect(() => { setOffset(0); }, [scope, q]);
  useEffect(() => {
    let alive = true; setLoading(true); setError('');
    Promise.all([api(`/memories?${query}&q=${encodeURIComponent(q)}&offset=${offset}`), api(`/settings/memory?${settingsQuery}`), api('/settings/memory')])
      .then(([list, setting, global]) => { if (alive) { setRows(list.items); setMore(list.has_more); setSettings(setting); setMaster(global); } })
      .catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [api, query, q, offset, reload]);
  async function mutate(action) {
    if (busy) return; setBusy(true); setError('');
    try { await action(); setReload(n => n + 1); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  function changeSetting(scopeData, row) {
    const assign = scopeData.scope === 'global' ? setMaster : setSettings;
    assign(previous => ({ ...previous, enabled: !row.enabled }));
    mutate(async () => {
      try { const saved = await api('/settings/memory', { method: 'PUT', ...jsonBody({ ...scopeData, enabled: !row.enabled, revision: row.revision }) }); assign(saved); }
      catch (e) { assign(row); throw e; }
    });
  }
  return <div className="memory-panel"><div className="ws-page-title"><div><span className="ws-eyebrow">YOUR CONTEXT, YOUR CHOICE</span><h2>Saved memories</h2><p>Private facts and preferences. Saved only when you ask.</p></div><button className="primary compact" disabled={busy} onClick={() => setRemember(true)}>+ Add memory</button></div>
    <ErrorNotice error={error} retry={() => setReload(n => n + 1)} />
    <div className="memory-settings">
      <label className="memory-check"><input type="checkbox" disabled={busy || !master} checked={!!master?.enabled} onChange={() => changeSetting({ scope: 'global' }, master)} />Use saved memories in AI responses</label>
      {['project', 'conversation'].includes(scope) && <label className="memory-check"><input type="checkbox" disabled={busy || !settings} checked={!!settings?.enabled} onChange={() => changeSetting(data, settings)} />Allow memory from this {scope}</label>}
      <small>Memory starts off. Disabling it keeps saved records and prevents injection into new answers. Manual actions use no AI calls.</small>
    </div>
    <div className="ws-toolbar"><input type="search" aria-label="Search memories" placeholder="Search saved memories…" value={q} onChange={e => setQ(e.target.value)} />
      <select aria-label="Memory scope" value={scope} onChange={e => setScope(e.target.value)}><option value="global">Global</option>{projectId && <option value="project">This project</option>}{conversationId && <option value="conversation">This conversation</option>}<option value="all">All saved memories</option></select></div>
    {loading ? <p role="status">Loading memories…</p> : <div className="memory-list">{rows.map(row => <article key={row.id} className="memory-card"><small>{row.scope} · {new Date(row.updated_at).toLocaleDateString()}</small><p>{row.content}</p>
      <div className="ws-form-actions"><button className="secondary" disabled={busy} onClick={() => { setEditing(row); setDraft(row.content); }}>Edit memory</button><button className="secondary danger" disabled={busy} onClick={() => {
        if (window.confirm('Forget this saved memory?')) mutate(() => api(`/memories/${row.id}`, { method: 'DELETE', ...jsonBody({ revision: row.revision }) }));
      }}>Forget this</button></div></article>)}{!rows.length && <Empty title="A little context goes a long way">Add a preference or use Remember this on a chat message.</Empty>}</div>}
    <div className="ws-form-actions"><button className="secondary" disabled={!offset || busy} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><button className="secondary" disabled={!more || busy} onClick={() => setOffset(offset + 50)}>Next</button>
      {scope !== 'all' && <button className="secondary danger" disabled={busy || !rows.length} onClick={() => { if (window.confirm(`Clear every saved memory in this ${scope} scope?`)) mutate(() => api('/memories/clear', { method: 'POST', ...jsonBody({ ...data, confirmation: 'CLEAR' }) })); }}>Clear scope…</button>}</div>
    {remember && <RememberDialog api={api} projectId={projectId} conversationId={conversationId} content="" onClose={() => { setRemember(false); setReload(n => n + 1); }} />}
    {editing && <Modal title="Edit memory" onClose={() => setEditing(null)} busy={busy}><form className="ws-form memory-form" onSubmit={e => { e.preventDefault(); mutate(async () => { await api(`/memories/${editing.id}`, { method: 'PATCH', ...jsonBody({ content: draft, consent: true, revision: editing.revision }) }); setEditing(null); }); }}><ErrorNotice error={error} /><label>Memory text<textarea aria-label="Memory text" rows={6} maxLength={4000} required value={draft} onChange={e => setDraft(e.target.value)} /></label><p>Saving approves this replacement text for future memory use.</p><button className="primary compact" disabled={busy || !draft.trim()}>Save approved changes</button></form></Modal>}
  </div>;
}
