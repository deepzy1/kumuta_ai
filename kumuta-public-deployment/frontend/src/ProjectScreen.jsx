import ProjectCanvas from './ProjectCanvas.jsx';
import React, { lazy, Suspense, useEffect, useState } from 'react';
import { jsonBody } from './api';
import Modal, { Empty, ErrorNotice } from './Modal';
import { ProjectMark, projectTabs, tabLabel } from './WorkspaceNav';
import { ProjectFields } from './WorkspaceDialogs';
import Tasks from './Tasks';
const DataAnalysis = lazy(() => import('./DataAnalysis'));
const Study = lazy(() => import('./Study'));
const Analytics = lazy(() => import('./Analytics'));
const Focus = lazy(() => import('./Focus'));
import Notes from './Notes';
import ProjectChats from './ProjectChats';
import MemoryPanel from './Memory';
import DocumentsPanel from './Documents';
import ProjectOverview from './ProjectOverview';
import ProjectDatasets from './ProjectDatasets';

export function ProjectsHome({ api, store, onProject, onCreate }) {
  const [search, setSearch] = useState(''), [archived, setArchived] = useState(false), [sort, setSort] = useState('updated');
  const [reporting, setReporting] = useState(false);
  const projects = store.projects.filter(p => p.archived === archived && `${p.name} ${p.description}`.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name) : b[sort === 'created' ? 'created_at' : 'updated_at'].localeCompare(a[sort === 'created' ? 'created_at' : 'updated_at']));
  return <div className="ws-page"><div className="ws-page-title"><div><span className="ws-eyebrow">A PLACE FOR YOUR IDEAS</span><h1>{store.workspace?.name || 'Your workspace'}</h1><p>Give every idea a little room to grow.</p></div>
    <button className="primary compact" disabled={!store.workspace} onClick={onCreate}>+ New project</button></div>
    <div className="ws-toolbar"><input type="search" aria-label="Search projects" placeholder="Search projects…" value={search} onChange={e => setSearch(e.target.value)} />
      <select aria-label="Sort projects" value={sort} onChange={e => setSort(e.target.value)}><option value="updated">Recently updated</option><option value="name">Name</option><option value="created">Newest first</option></select>
      <button className="secondary" aria-pressed={archived} onClick={() => setArchived(!archived)}>{archived ? 'Show active' : 'Archived'}</button></div>
    <button className="secondary" onClick={() => setReporting(!reporting)}>{reporting ? 'Hide workspace analytics' : 'Workspace analytics'}</button>
    {reporting && store.workspace && <Suspense fallback={<p role="status">Loading analytics…</p>}><Analytics key={store.workspace.id} api={api} workspaceId={store.workspace.id} /></Suspense>}
    <ErrorNotice error={store.error} retry={store.refreshProjects} />
    {store.loading ? <p className="ws-loading" role="status">Loading your projects…</p> : <>
      <div className="ws-project-grid">{projects.map(project => <button className="ws-project-card" key={project.id} onClick={() => onProject(project.id)}>
        <ProjectMark project={project} /><h2>{project.name}</h2><p>{project.description || 'A fresh start. Add a description to set the direction.'}</p>
        <small>{project.archived ? 'Archived' : 'Open project'} <span aria-hidden="true">↗</span></small>
      </button>)}</div>
      {!projects.length && <Empty title={search ? 'No matching projects' : archived ? 'Nothing archived' : 'A fresh canvas for your next project'}>{search ? 'Try another search.' : archived ? 'Archived projects will appear here.' : 'Create a project to bring your chats, tasks and notes together.'}</Empty>}
    </>}
  </div>;
}

export default function ProjectScreen({ api, projectId, tab, onTab, onNewChat, onChat, onMoveChat, onChanged, onDeleted, registerGuard, onAskDocuments, onTutor, onAssist, onFocusScreen, onAccountSettings, settingsSection, initialItemId }) {
  const [resourceTask, setResourceTask] = useState(null);
  useEffect(()=>{if(tab==='tasks'&&initialItemId)setResourceTask(initialItemId);},[tab,initialItemId]);
  const [focusTask, setFocusTask] = useState(null);
  const [studySource,setStudySource]=useState(null),[datasetSource,setDatasetSource]=useState(null);
  const [libraryVersion,setLibraryVersion]=useState(0);
  const [reports, setReports] = useState(false);
  const [project, setProject] = useState(null), [error, setError] = useState(''), [reload, setReload] = useState(0);
  useEffect(() => {
    let alive = true; setProject(null); setError('');
    api(`/projects/${projectId}`).then(row => { if (alive) setProject(row); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [api, projectId, reload]);
  useEffect(() => {
    if (tab !== 'overview' || project?.id !== projectId) return;
    let alive = true;
    api(`/projects/${projectId}`).then(row => { if (alive) setProject(row); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [api, projectId, tab]);
  if (!project) return <div className="ws-page"><ErrorNotice error={error} retry={() => setReload(n => n + 1)} />{!error && <p role="status">Loading project…</p>}</div>;
  async function changed(row) { setProject({ ...project, ...row }); await onChanged(); }
  return <div className="ws-project-shell">{project.archived && <p className="ws-info">Archived project · restore in Settings to make changes.</p>}
    <nav className="ws-tabs" aria-label="Project sections">{projectTabs.map(value => <button key={value} className={tab === value ? 'active' : ''} aria-current={tab === value ? 'page' : undefined} onClick={() => value === 'chats' ? onNewChat(project) : onTab(value)}>{tabLabel(value)}</button>)}</nav>
    <div className="ws-project-content">
      <ErrorNotice error={error} retry={() => setReload(n => n + 1)} />
      <ModuleBoundary key={`${projectId}-${tab}`}><Suspense fallback={<p role="status">Loading module…</p>}>
      {tab === 'canvas' && <ProjectCanvas api={api} project={project} />}
      {tab === 'overview' && <><ProjectOverview api={api} project={project} onTab={onTab} onNewChat={() => onNewChat(project)} onReports={() => setReports(!reports)} />{reports && <Analytics api={api} projectId={projectId} />}</>}
      {tab === 'study' && <Study initialDocumentId={studySource} onSourceConsumed={()=>setStudySource(null)} key={projectId} api={api} project={project} registerGuard={registerGuard} onTasks={() => onTab('tasks')} onTutor={(controls, prompt) => onTutor(project, controls, prompt)} />}
      {tab === 'focus' && <Focus initialTaskId={focusTask} key={projectId} api={api} project={project} registerGuard={registerGuard} onExit={() => onTab('overview')} onTasks={() => onTab('tasks')} onFocusScreen={onFocusScreen} onAssist={prompt => onAssist(project, prompt)} />}
      {(tab === 'data' || tab === 'reports') && <DataAnalysis initialDatasetId={datasetSource} key={`${projectId}-${tab}`} initialView={tab === 'reports' ? 'Reports' : 'Datasets'} api={api} project={project} registerGuard={registerGuard} />}
      {tab === 'tasks' && <Tasks onFocus={id=>{setFocusTask(id);onTab('focus');}} initialTaskId={resourceTask} onSelectionClose={() => setResourceTask(null)} key={projectId} api={api} project={project} registerGuard={registerGuard} />}
      {tab === 'notes' && <Notes initialNoteId={tab==='notes'?initialItemId:undefined} key={projectId} api={api} project={project} registerGuard={registerGuard} />}
      {tab === 'chats' && <ProjectChats key={projectId} api={api} project={project} onNewChat={() => onNewChat(project)} onChat={onChat} onMoveChat={onMoveChat} />}
      {tab === 'documents' && <><DocumentsPanel onStudy={id=>{setStudySource(id);onTab('study');}} onChat={onChat} onTask={id => { setResourceTask(id); onTab('tasks'); }} key={`${projectId}-${libraryVersion}`} api={api} projectId={projectId} archived={project.archived} registerGuard={registerGuard} onAsk={(ids, mode) => onAskDocuments(project, ids, mode)} />
        <ProjectDatasets api={api} projectId={projectId} onOpen={id=>{setDatasetSource(typeof id==='number'?id:null);onTab('data');}} /><details open className="doc-legacy"><summary>Existing chat attachments</summary><ProjectChats onLibraryChanged={()=>setLibraryVersion(v=>v+1)} api={api} project={project} documents onNewChat={() => onNewChat(project)} onChat={onChat} onMoveChat={onMoveChat} /></details></>}
      {tab === 'settings' && <ProjectSettings key={projectId} initialSection={settingsSection} onAccountSettings={onAccountSettings} onDocuments={() => onTab('documents')} api={api} project={project} onChanged={changed} onDeleted={onDeleted} registerGuard={registerGuard} />}
      </Suspense></ModuleBoundary>
    </div>
  </div>;
}

class ModuleBoundary extends React.Component {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<div role="alert"><p>This module could not be loaded. Your saved work is retained.</p><button className="secondary" onClick={()=>window.location.reload()}>Reload application</button></div>:this.props.children;}
}

function ProjectSettings({ api, project, onChanged, onDeleted, registerGuard, initialSection, onAccountSettings, onDocuments }) {
  const [section, setSection] = useState(initialSection || 'general');
  const [draft, setDraft] = useState({ name: project.name, description: project.description, icon: project.icon, color: project.color });
  const [baseline, setBaseline] = useState(JSON.stringify(draft));
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [deleting, setDeleting] = useState(false), [confirm, setConfirm] = useState('');
  const dirty = JSON.stringify(draft) !== baseline;
  useEffect(() => registerGuard(() => !busy && (!dirty || window.confirm('Discard unsaved project settings?'))), [registerGuard, dirty, busy]);
  useEffect(() => {
    const before = e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before);
  }, [dirty]);
  async function save(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try { const row = await api(`/projects/${project.id}`, { method: 'PATCH', ...jsonBody({ ...draft, revision: project.revision }) });
      setBaseline(JSON.stringify(draft)); await onChanged(row);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function archive() {
    if (busy || (dirty && !window.confirm('Discard unsaved settings and change archive status?'))) return;
    setBusy(true); setError('');
    try { const row = await api(`/projects/${project.id}`, { method: 'PATCH', ...jsonBody({ archived: !project.archived, revision: project.revision }) });
      const fresh = { name: row.name, description: row.description, icon: row.icon, color: row.color };
      setDraft(fresh); setBaseline(JSON.stringify(fresh)); await onChanged(row);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function remove() {
    if (busy) return; setBusy(true); setError('');
    try { await api(`/projects/${project.id}`, { method: 'DELETE', ...jsonBody({ revision: project.revision, confirm_name: confirm }) });
      setDeleting(false); onDeleted();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="project-settings-layout"><nav className="settings-categories" aria-label="Project settings categories">{[['general','General'],['models','AI & Models'],['memory','AI & Memory'],['files','Files'],['privacy','Privacy / Access'],['advanced','Advanced']].map(([id,label]) => <button key={id} className={section === id ? 'selected' : ''} onClick={() => { if (!dirty || window.confirm('Keep unsaved project settings while switching category?')) setSection(id); }}>{label}</button>)}</nav><div className="ws-settings">
    {section === 'memory' && <MemoryPanel api={api} projectId={project.id} />}
    {section === 'models' && <section className="settings-category-content"><h2>AI &amp; Models</h2><p>Manage your provider key, preferred model and usage.</p><button className="secondary" onClick={() => onAccountSettings('key')}>My API Key</button><button className="secondary" onClick={() => onAccountSettings('usage')}>Usage &amp; Limits</button></section>}
    {section === 'files' && <section className="settings-category-content"><h2>Files</h2><p>Manage the project library, processing status and stored files.</p><button className="secondary" onClick={onDocuments}>Open project documents</button></section>}
    {section === 'privacy' && <section className="settings-category-content"><h2>Privacy / Access</h2><p>This project, its conversations, notes and files are private to your account. Memory is used only with your saved consent settings.</p><button className="secondary" onClick={() => setSection('memory')}>Review AI &amp; Memory</button></section>}
    <form hidden={section !== 'general'} className="ws-form" onSubmit={save}><h2>Project settings</h2><ErrorNotice error={error} /><ProjectFields draft={draft} setDraft={setDraft} />
    <div className="ws-form-actions"><span className="muted" role="status">{dirty ? 'Unsaved changes' : 'All changes saved'}</span><button className="primary compact" disabled={busy || !dirty || !draft.name.trim()}>{busy ? 'Saving…' : 'Save changes'}</button></div></form>
    <section hidden={section !== 'advanced'} className="ws-settings-section"><h3>{project.archived ? 'Restore project' : 'Archive project'}</h3><p>Archived projects remain available to read, including their chats.</p><button className="secondary" disabled={busy} onClick={archive}>{project.archived ? 'Restore project' : 'Archive project'}</button></section>
    <section hidden={section !== 'advanced'} className="ws-danger-zone"><h3>Delete project</h3><p>Tasks, notes, managed project documents, datasets, reports, Study and Focus records will be deleted. Conversations and their conversation-scoped attachments stay in your chat history.</p><button className="secondary danger" disabled={busy} onClick={() => setDeleting(true)}>Delete project…</button></section>
    {deleting && <Modal title="Delete project" onClose={() => setDeleting(false)} busy={busy}><div className="ws-form"><ErrorNotice error={error} /><p>This permanently deletes project tasks, notes, managed documents, datasets, reports, Study and Focus records. Chats and their conversation-scoped files are preserved.</p><label>Type “{project.name}” to confirm<input value={confirm} onChange={e => setConfirm(e.target.value)} /></label><div className="ws-form-actions"><button className="secondary" onClick={() => setDeleting(false)} disabled={busy}>Cancel</button><button className="secondary danger" disabled={busy || confirm !== project.name} onClick={remove}>Delete project</button></div></div></Modal>}
  </div></div>;
}
