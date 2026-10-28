import React, { useEffect, useRef, useState } from 'react';
import { Pin, StickyNote } from 'lucide-react';
import { jsonBody } from './api';
import { allPages } from './workspaceData';
import Modal, { Empty, ErrorNotice } from './Modal';
const draftOf = note => ({ title: note.title, content: note.content, pinned: !!note.pinned });

export default function Notes({ api, project, registerGuard, initialNoteId }) {
  const [notes, setNotes] = useState([]), [query, setQuery] = useState(''), [quick, setQuick] = useState('');
  const [note, setNote] = useState(null), [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [saveError, setSaveError] = useState(''), [deleting, setDeleting] = useState(false);
  const writing = useRef(false), alive = useRef(true), currentDraft = useRef(draft);
  currentDraft.current = draft;
  const dirty = !!note && JSON.stringify(draft) !== JSON.stringify(draftOf(note));
  const leave = () => !writing.current && (!dirty || window.confirm('Discard unsaved note changes?'));
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => registerGuard(leave), [registerGuard, dirty, busy]);
  useEffect(() => {
    const before = e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before);
  }, [dirty]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);
    const timer = setTimeout(() => allPages(api, `/projects/${project.id}/notes?q=${encodeURIComponent(query)}`, { signal: controller.signal })
      .then(rows => { if (!controller.signal.aborted) setNotes(rows); }).catch(e => { if (e.name !== 'AbortError') setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); }), 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, project.id, query]);
  useEffect(()=>{if(initialNoteId)select(initialNoteId);},[initialNoteId]);
  async function refresh() { const rows = await allPages(api, `/projects/${project.id}/notes?q=${encodeURIComponent(query)}`); if (alive.current) setNotes(rows); }
  async function select(id) {
    if (!leave()) return; writing.current = true; setBusy(true); setError(''); setSaveError('');
    try { const row = await api(`/projects/${project.id}/notes/${id}`); setNote(row); setDraft(draftOf(row)); }
    catch (e) { setError(e.message); } finally { writing.current = false; setBusy(false); }
  }
  async function create(event) {
    event?.preventDefault(); if (!leave() || project.archived) return;
    writing.current = true; setBusy(true); setError(''); setSaveError('');
    try { const row = await api(`/projects/${project.id}/notes`, { method: 'POST', ...jsonBody({ title: quick.trim() || 'Untitled note' }) }); setNote(row); setDraft(draftOf(row)); setQuick(''); await refresh(); }
    catch (e) { setError(e.message); } finally { writing.current = false; setBusy(false); }
  }
  async function save(event) {
    event?.preventDefault(); if (writing.current || !note || !draft.title.trim() || project.archived) return;
    writing.current = true; setBusy(true); setSaveError('');
    const snapshot = draft;
    try {
      const row = await api(`/projects/${project.id}/notes/${note.id}`, { method: 'PUT', ...jsonBody({ ...snapshot, revision: note.revision }) });
      if (!alive.current) return;
      setNote(row);
      // Typing during a save must never be overwritten by an older response.
      if (JSON.stringify(currentDraft.current) === JSON.stringify(snapshot)) setDraft(draftOf(row));
      await refresh();
    } catch (e) { if (alive.current) setSaveError(e.message); }
    finally { writing.current = false; if (alive.current) setBusy(false); }
  }
  useEffect(() => {
    if (!dirty || busy || saveError || !draft.title.trim() || project.archived || deleting) return;
    const timer = setTimeout(() => save(), 750); return () => clearTimeout(timer);
  }, [dirty, draft, busy, note, saveError, deleting]);
  function edit(values) { setDraft(previous => ({ ...previous, ...values })); setSaveError(''); }
  function close() { if (leave()) { setNote(null); setDraft(null); setSaveError(''); } }
  async function remove() {
    if (writing.current) return; writing.current = true; setBusy(true); setSaveError('');
    try { await api(`/projects/${project.id}/notes/${note.id}`, { method: 'DELETE', ...jsonBody({ revision: note.revision }) }); setNote(null); setDraft(null); setDeleting(false); await refresh(); }
    catch (e) { setSaveError(e.message); } finally { writing.current = false; setBusy(false); }
  }
  return <section className="notes-workspace"><div className="ws-section-heading"><div><h1>Notes</h1><p className="muted">Capture and organize your ideas.</p></div><button className="primary compact" disabled={busy || project.archived} onClick={create}>+ New note</button></div>
    <form className="note-quick-composer" onSubmit={create}><StickyNote size={20} /><input aria-label="Quick note title" maxLength={200} placeholder="Take a note…" value={quick} disabled={busy || project.archived} onChange={e => setQuick(e.target.value)} /><button className="secondary" disabled={busy || project.archived || !quick.trim()}>Create note</button></form>
    <div className="ws-toolbar"><input type="search" aria-label="Search notes" placeholder="Search titles and text…" value={query} onChange={e => setQuery(e.target.value)} /></div><ErrorNotice error={error} retry={refresh} />
    {loading && <p role="status">Loading notes…</p>}
    <div className="notes-grid">{notes.map(row => <button className={`note-card ${row.pinned ? 'pinned' : ''}`} key={row.id} disabled={busy} onClick={() => select(row.id)}><strong>{row.title}{row.pinned && <Pin size={16} aria-label="Pinned note" />}</strong><p>{row.excerpt || 'Open to add your thoughts.'}</p><small>Edited {new Date(row.updated_at).toLocaleDateString()}</small></button>)}</div>
    {!loading && !notes.length && <Empty title={query ? 'No matching notes' : 'Capture your first thought'}>Use the quick composer to create a note.</Empty>}
    {note && <Modal title={deleting ? 'Delete note' : 'Edit note'} onClose={close} busy={busy} wide><div className="ws-form"><ErrorNotice error={saveError} />
      {deleting ? <><p>Delete “{note.title}”? This cannot be undone.</p><div className="ws-form-actions"><button className="secondary" disabled={busy} onClick={() => setDeleting(false)}>Cancel</button><button className="secondary danger" disabled={busy} onClick={remove}>Delete note</button></div></> : <form className="ws-form" onSubmit={save}>
        <label>Note title<input required maxLength={200} value={draft.title} disabled={project.archived} onChange={e => edit({ title: e.target.value })} /></label><label>Note text<textarea rows={12} maxLength={100000} value={draft.content} disabled={project.archived} onChange={e => edit({ content: e.target.value })} /></label>
        {draft.content.split('\n').some(line => /^- \[[ xX]\] /.test(line)) && <section className="note-checklist" aria-label="Note checklist"><h3>Checklist</h3>{draft.content.split('\n').map((line, index) => { const match = /^- \[([ xX])\] (.*)$/.exec(line); return match && <label key={index}><input type="checkbox" disabled={project.archived} checked={match[1].toLowerCase() === 'x'} onChange={e => edit({ content: draft.content.split('\n').map((text, n) => n === index ? `- [${e.target.checked ? 'x' : ' '}] ${match[2]}` : text).join('\n') })} />{match[2] || `Checklist item ${index + 1}`}</label>; })}</section>}
        <div className="ws-form-actions"><button type="button" className="secondary" aria-pressed={draft.pinned} disabled={project.archived} onClick={() => edit({ pinned: !draft.pinned })}><Pin size={16} />{draft.pinned ? 'Unpin note' : 'Pin note'}</button><button type="button" className="secondary" disabled={project.archived || draft.content.length > 99990} onClick={() => edit({ content: draft.content + '\n- [ ] ' })}>Add checklist</button></div>
        <div className="ws-form-actions"><span className="muted" role="status">{saveError ? 'Save failed · draft kept' : busy ? 'Saving…' : dirty ? 'Unsaved changes · autosaving' : 'Saved'}</span><button type="button" className="secondary danger" disabled={busy || project.archived} onClick={() => setDeleting(true)}>Delete</button><button className="primary compact" disabled={busy || !dirty || !draft.title.trim() || project.archived}>Save note</button><button type="button" className="secondary" disabled={busy || dirty} onClick={close}>Done</button></div>
        {saveError && <button type="button" className="secondary" disabled={busy} onClick={() => select(note.id)}>Reload saved version…</button>}
      </form>}
    </div></Modal>}
  </section>;
}
