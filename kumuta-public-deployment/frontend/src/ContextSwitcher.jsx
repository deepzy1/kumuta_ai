import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Search, Folder, MessageSquare, Plus, Settings2 } from 'lucide-react';
import { ProjectMark } from './WorkspaceNav';
export default function ContextSwitcher({ store, projectId, disabled, onWorkspace, onProject, onGeneral, onAction }) {
  const [open, setOpen] = useState(false), [query, setQuery] = useState('');
  const root = useRef(null), trigger = useRef(null);
  const project = store.projects.find(p => p.id === projectId);
  useEffect(() => {
    if (!open) return;
    const outside = e => { if (!root.current?.contains(e.target)) setOpen(false); };
    const key = e => { if (e.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', key); };
  }, [open]);
  function choose(action) { action(); setOpen(false); setQuery(''); trigger.current?.focus(); }
  return <div className="context-switcher" ref={root}>
    <button ref={trigger} className="context-trigger" aria-label="Switch project or workspace" aria-expanded={open} disabled={disabled} onClick={() => setOpen(!open)}>
      {project ? <ProjectMark project={project} /> : <MessageSquare size={17} />}<span>{project?.name || 'General Chat'}</span><ChevronDown size={15} />
    </button>
    {open && <section className="context-menu" aria-label="Project and workspace switcher">
      <label className="ws-switch"><span>Workspace</span><select aria-label="Switch workspace" value={store.workspaceId || ''} disabled={disabled} onChange={e => { onWorkspace(Number(e.target.value)); setQuery(''); }}>
        {store.workspaces.map(w => <option key={w.id} value={w.id}>{w.name}{w.is_personal ? ' · Personal' : ''}</option>)}
      </select></label>
      <div className="context-search"><Search size={16} /><input autoFocus type="search" aria-label="Search projects and workspaces" placeholder="Find a project or workspace…" value={query} onChange={e => setQuery(e.target.value)} /></div>
      <button className="context-option" onClick={() => choose(onGeneral)}><MessageSquare size={17} />General Chat</button>
      <div className="context-options">
        {query && store.workspaces.filter(w => w.name.toLowerCase().includes(query.toLowerCase())).map(w => <button className="context-option" key={`w${w.id}`} onClick={() => { onWorkspace(w.id); setQuery(''); }}><Folder size={17} />{w.name}<small>Workspace</small></button>)}
        {store.projects.filter(p => !p.archived && p.name.toLowerCase().includes(query.toLowerCase())).map(p => <button className={`context-option ${p.id === projectId ? 'selected' : ''}`} key={p.id} onClick={() => choose(() => onProject(p))}><ProjectMark project={p} />{p.name}</button>)}
        {store.loading && <p role="status">Loading projects…</p>}
        {!store.loading && !store.projects.some(p => !p.archived && p.name.toLowerCase().includes(query.toLowerCase())) && <p className="muted">No matching projects.</p>}
      </div>
      <div className="context-management"><button onClick={() => choose(() => onAction('project-create'))}><Plus size={16} />New project</button><button onClick={() => choose(() => onAction('workspace-create'))}><Plus size={16} />Workspace</button><button onClick={() => choose(() => onAction('workspace-settings'))}><Settings2 size={16} />Manage</button></div>
    </section>}
  </div>;
}
