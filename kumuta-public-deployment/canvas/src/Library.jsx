import React, { useEffect, useRef, useState } from 'react';
import { jsonBody } from '@kumuta/api.js';
import { allPages } from '@kumuta/workspaceData.js';
import Modal, { ErrorNotice } from '@kumuta/Modal.jsx';
import { visibleBoards } from './navigation.js';

function BoardMark() { return <svg viewBox="0 0 200 112" aria-hidden="true"><path d="M69 56h62M100 39v34" stroke="#FF6500" strokeWidth="2"/><rect x="20" y="35" width="49" height="42" rx="7"/><rect x="131" y="35" width="49" height="42" rx="7"/><rect x="78" y="8" width="44" height="31" rx="7"/><rect x="78" y="73" width="44" height="31" rx="7"/></svg>; }
export default function Library({ api, route, workspaces, navigate, onRefresh }) {
  const workspaceId = route.workspaceId || workspaces[0]?.id;
  const projectId = route.projectId || null;
  const authorized = workspaces.some(w => w.id === workspaceId);
  const [projects, setProjects] = useState([]), [projectsBusy, setProjectsBusy] = useState(false), [projectError, setProjectError] = useState('');
  const [rows, setRows] = useState([]), [hasMore, setHasMore] = useState(false), [busy, setBusy] = useState(true), [error, setError] = useState('');
  const [status, setStatus] = useState('active'), [search, setSearch] = useState(''), [sort, setSort] = useState('updated'), [reload, setReload] = useState(0);
  const [dialog, setDialog] = useState(null), [mutationBusy, setMutationBusy] = useState(false), [mutationError, setMutationError] = useState('');
  const offset = useRef(0), generation = useRef(0);
  const project = projects.find(p => p.id === projectId);
  useEffect(() => {
    const abort = new AbortController(); let active = true; setProjectsBusy(true); setProjectError(''); setProjects([]);
    if (authorized) Promise.all([allPages(api, `/workspaces/${workspaceId}/projects`, { signal:abort.signal }), allPages(api, `/workspaces/${workspaceId}/projects?archived=true`, { signal:abort.signal })]).then(([a,b])=> { if (active) setProjects([...a,...b]); }).catch(e=> { if (active) setProjectError(e.message); }).finally(()=> { if (active) setProjectsBusy(false); });
    else setProjectsBusy(false);
    return () => { active = false; abort.abort(); };
  }, [api, workspaceId, authorized, reload]);
  const path = `/boards?workspace_id=${workspaceId}${projectId ? `&project_id=${projectId}` : ''}&status=${status}&limit=24`;
  async function load(append, epoch = generation.current, signal) {
    setBusy(true); setError('');
    try {
      const page = await api(`${path}&offset=${append ? offset.current : 0}`, { signal });
      if (generation.current !== epoch) return;
      offset.current = (append ? offset.current : 0) + page.items.length;
      setRows(old => [...new Map([...(append ? old : []), ...page.items].map(b=>[b.id,b])).values()]); setHasMore(page.has_more);
    } catch (e) { if (generation.current === epoch) setError(e.message); }
    finally { if (generation.current === epoch) setBusy(false); }
  }
  useEffect(() => {
    const epoch = ++generation.current, abort = new AbortController(); setRows([]); offset.current=0; setHasMore(false);
    if (authorized) load(false, epoch, abort.signal); else { setError('Workspace unavailable. Select an authorized workspace.'); setBusy(false); }
    return () => { generation.current++; abort.abort(); };
  }, [api, path, reload, authorized]);
  function openDialog(value) { setMutationError(''); setDialog(value); }
  async function mutate(event) {
    event.preventDefault(); setMutationBusy(true); setMutationError('');
    const title = new FormData(event.currentTarget).get('title')?.trim();
    try {
      if (dialog.kind === 'create') {
        const board = await api('/boards', { method:'POST', ...jsonBody({ workspace_id:workspaceId, ...(projectId ? {project_id:projectId}:{}), title }) });
        setDialog(null); navigate({boardId:board.id});
      } else {
        await api(`/boards/${dialog.board.id}`, { method:'PATCH', ...jsonBody(dialog.kind === 'rename' ? {title} : {status: dialog.board.status === 'active' ? 'archived' : 'active'}) });
        setDialog(null); setReload(n=>n+1);
      }
    } catch (e) { setMutationError(e.message); } finally { setMutationBusy(false); }
  }
  const shown = visibleBoards(rows, search, sort);
  return <div className="library-layout">
    <aside className="library-nav"><span className="eyebrow">YOUR WORKSPACE</span><label>Workspace<select aria-label="Workspace" value={workspaceId} onChange={e=>navigate({workspaceId:Number(e.target.value)})}>{!authorized && <option value={workspaceId}>Unavailable workspace</option>}{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <button className={status === 'active' ? 'selected' : ''} onClick={()=>setStatus('active')}>▧ <span>All boards</span></button><button className={status === 'archived' ? 'selected' : ''} onClick={()=>setStatus('archived')}>▤ <span>Archived</span></button>
      <label>Project<select aria-label="Project" value={projectId || ''} disabled={projectsBusy || !!projectError} onChange={e=>navigate({workspaceId,projectId:Number(e.target.value)||null})}><option value="">All projects</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}{p.archived ? ' (archived)' : ''}</option>)}</select></label><ErrorNotice error={projectError} retry={()=>setReload(n=>n+1)} />
      <p className="library-note">A little space.<br />A world of possibilities.</p>
    </aside>
    <main className="library-main"><div className="library-heading"><div><span className="eyebrow">VISUALIZE · PLAN · CREATE</span><h1>{status === 'archived' ? 'Archived boards' : 'Your canvas'}</h1><p>{project?.name || workspaces.find(w=>w.id===workspaceId)?.name || 'Workspace unavailable'} <span className="separator">/</span> Make your ideas visible.</p></div><button className="primary" aria-label="New board" disabled={!authorized || projectsBusy || !!projectError || !!project?.archived || (!!projectId && !project)} onClick={()=>openDialog({kind:'create'})}>＋ New board</button></div>
      <div className="library-tools"><div className="library-tabs"><button className={status === 'active' ? 'current' : ''} onClick={()=>setStatus('active')}>Boards</button><button className={status === 'archived' ? 'current' : ''} onClick={()=>setStatus('archived')}>Archived</button></div><label className="search-label"><span aria-hidden="true">⌕</span><input aria-label="Search loaded boards" placeholder="Search loaded boards…" value={search} onChange={e=>setSearch(e.target.value)} /></label><select aria-label="Sort loaded boards" value={sort} onChange={e=>setSort(e.target.value)}><option value="updated">Last updated</option><option value="created">Newest created</option><option value="name">Name A–Z</option></select><button aria-label="Refresh boards" onClick={()=>{onRefresh();setReload(n=>n+1);}}>↻</button></div>
      <p className="collection-count">{rows.length} boards loaded{hasMore ? ' · More available' : ''} · Search and sort apply to loaded boards</p><ErrorNotice error={error} retry={()=>setReload(n=>n+1)} />
      {busy && !rows.length ? <div className="library-empty" role="status">Loading your boards…</div> : !shown.length && !error ? <div className="library-empty"><BoardMark /><h2>{search ? 'No matching loaded boards' : status === 'archived' ? 'Your archive is empty' : 'A fresh canvas awaits'}</h2><p>{search ? 'Try another search, or load more boards.' : status === 'archived' ? 'Archived boards stay here, ready when you need them.' : 'Start with a thought. Give it a little room to grow.'}</p>{!search && status === 'active' && <button className="primary" disabled={!authorized || projectsBusy || !!projectError || !!project?.archived || (!!projectId && !project)} onClick={()=>openDialog({kind:'create'})}>＋ Create your first board</button>}</div> : <div className="board-grid">{shown.map(b=><article className="board-card" key={b.id}><button className="board-open" onClick={()=>navigate({boardId:b.id})} aria-label={`Open ${b.title}`}><div className="board-preview"><BoardMark /><span>{b.status === 'archived' ? 'Archived · Read only' : 'EXCALIDRAW BOARD'}</span></div><div className="board-info"><h2>{b.title}</h2><p>▱ {projects.find(p=>p.id===b.project_id)?.name || (b.project_id ? 'Project board' : 'Workspace board')}</p><small>Updated {new Date(b.updated_at).toLocaleDateString()} · v{b.current_revision}</small></div></button><div className="board-actions"><button onClick={()=>openDialog({kind:'rename',board:b})} aria-label={`Rename ${b.title}`}>Rename</button><button onClick={()=>openDialog({kind:'status',board:b})} aria-label={`${b.status==='active'?'Archive':'Restore'} ${b.title}`}>{b.status==='active'?'Archive':'Restore'}</button></div></article>)}</div>}
      {hasMore && <button className="load-more" disabled={busy} onClick={()=>load(true)}>{busy ? 'Loading…' : 'Load more boards'}</button>}
    </main>
    {dialog && <Modal title={dialog.kind === 'create' ? 'New board' : dialog.kind === 'rename' ? 'Rename board' : dialog.board.status==='active' ? 'Archive board' : 'Restore board'} onClose={()=>setDialog(null)} busy={mutationBusy}><form className="dialog-form" onSubmit={mutate}>{dialog.kind !== 'status' ? <label>Board name<input name="title" defaultValue={dialog.board?.title || ''} placeholder="Untitled board" maxLength={200} required autoFocus /></label> : <p>{dialog.board.status==='active' ? 'Archive this board? Its scene and history will remain available in read-only mode.' : 'Restore this board to your active library?'}</p>}<ErrorNotice error={mutationError} /><footer><button type="button" disabled={mutationBusy} onClick={()=>setDialog(null)}>Cancel</button><button className="primary" disabled={mutationBusy}>{mutationBusy ? 'Saving…' : dialog.kind === 'create' ? 'Create board' : dialog.kind === 'rename' ? 'Save name' : 'Confirm'}</button></footer></form></Modal>}
  </div>;
}
