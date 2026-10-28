import React, { useEffect, useState } from 'react';
import Modal, { ErrorNotice } from './Modal';
import { jsonBody } from './api';
import { allPages } from './workspaceData';

const icons = ['folder', 'code', 'book', 'briefcase', 'star', 'home', 'target'];
export function ProjectFields({ draft, setDraft }) {
  const field = key => ({ value: draft[key], onChange: e => setDraft({ ...draft, [key]: e.target.value }) });
  return <>
    <label>Project name<input required maxLength={120} {...field('name')} /></label>
    <label>Description<textarea rows={4} maxLength={5000} {...field('description')} placeholder="What are you working toward?" /></label>
    <div className="ws-form-row"><label>Icon<select {...field('icon')}>{icons.map(icon => <option key={icon}>{icon}</option>)}</select></label>
      <label>Color<input type="color" {...field('color')} /></label></div>
  </>;
}

export function WorkspaceDialog({ type, store, api, onClose, onCreated, onDeleted }) {
  const editing = type === 'workspace-settings';
  const project = type === 'project-create';
  const [draft, setDraft] = useState({ name: editing ? store.workspace.name : '', description: '', icon: 'folder', color: '#ea580c' });
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function save(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {
      const row = await api(project ? `/workspaces/${store.workspaceId}/projects` : editing ? `/workspaces/${store.workspaceId}` : '/workspaces', {
        method: editing ? 'PATCH' : 'POST', ...jsonBody(project ? draft : { name: draft.name, ...(editing ? { revision: store.workspace.revision } : {}) }),
      });
      if (project) { await store.refreshProjects(); onCreated(row); }
      else { await store.refreshWorkspaces(); if (!editing) store.setWorkspaceId(row.id); }
      onClose();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function remove() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await api(`/workspaces/${store.workspaceId}`, { method: 'DELETE', ...jsonBody({ revision: store.workspace.revision, confirm_name: confirm }) });
      await store.refreshWorkspaces(); onDeleted(); onClose();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Modal title={project ? 'New project' : editing ? 'Workspace settings' : 'New workspace'} onClose={onClose} busy={busy}>
    <form className="ws-form" onSubmit={save}>
      <ErrorNotice error={error} />
      {project ? <ProjectFields draft={draft} setDraft={setDraft} /> : <label>Workspace name<input autoComplete="off" required maxLength={100} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>}
      <p className="muted">{project ? 'Chats, tasks and notes, together in one place.' : 'Workspaces are private to your account.'}</p>
      <div className="ws-form-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button><button className="primary compact" disabled={busy || !draft.name.trim()}>{busy ? 'Saving…' : editing ? 'Save changes' : project ? 'Create project' : 'Create workspace'}</button></div>
    </form>
    {editing && !store.workspace.is_personal && <div className="ws-danger-zone"><h3>Delete workspace</h3><p>Projects, tasks and notes will be deleted. Chats will remain in your history.</p>
      <label>Type “{store.workspace.name}” to confirm<input value={confirm} onChange={e => setConfirm(e.target.value)} /></label>
      <button className="secondary danger" disabled={busy || confirm !== store.workspace.name} onClick={remove}>Delete workspace</button>
    </div>}
  </Modal>;
}

export function MoveChatDialog({ api, conversation, store, onClose, onSaved }) {
  const [wid, setWid] = useState(store.workspaceId);
  const [projects, setProjects] = useState([]), [destination, setDestination] = useState('');
  const [current, setCurrent] = useState(conversation);
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    setLoading(true); setProjects([]); setDestination('');
    allPages(api, `/workspaces/${wid}/projects`).then(rows => { if (alive) setProjects(rows); })
      .catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [api, wid]);
  async function save(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await api(`/conversations/${current.id}/project`, { method: 'PATCH',
        ...jsonBody({ project_id: destination ? Number(destination) : null, expected_project_id: current.project_id ?? null }) });
      onSaved(result, projects.find(p => p.id === result.project_id) || null); onClose();
    } catch (e) {
      setError(e.message);
      if (e.status === 409) {
        try { setCurrent(await api(`/conversations/${current.id}`)); } catch { /* keep original error */ }
      }
    } finally { setBusy(false); }
  }
  return <Modal title="Move conversation" onClose={onClose} busy={busy}><form className="ws-form" onSubmit={save}>
    <p className="muted">Choose a project, or keep this conversation in general chat. Its messages and attachments stay together.</p><ErrorNotice error={error} />
    <label>Workspace<select value={wid || ''} onChange={e => setWid(Number(e.target.value))}>{store.workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
    <label>Destination<select value={destination} onChange={e => setDestination(e.target.value)} disabled={loading}>
      <option value="">General chat · no project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
    {loading && <p role="status">Loading projects…</p>}
    <div className="ws-form-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button><button className="primary compact" disabled={busy || loading}>{busy ? 'Moving…' : 'Move conversation'}</button></div>
  </form></Modal>;
}
