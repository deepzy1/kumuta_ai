import React, { useCallback, useEffect, useRef, useState } from 'react';
import { jsonBody } from './api';
import TaskDocuments from './TaskDocuments';
import Modal, { Empty, ErrorNotice } from './Modal';
import { loadBoard, taskMove, visibleTasks } from './workspaceData';
import useBoardDrag from './useBoardDrag';

const priorities = ['none', 'low', 'medium', 'high', 'urgent'];
const dateLabel = value => new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
function TaskBadge({ task }) {
  return <div className="ws-task-meta">{task.priority !== 'none' && <span className={`ws-priority ${task.priority}`}>{task.priority}</span>}
    {task.due_date && <time dateTime={task.due_date}>{dateLabel(task.due_date)}</time>}
    {(task.checklist.length > 0 || task.subtask_count > 0) && <span>{task.completion_percentage}% complete</span>}</div>;
}

export default function Tasks({ api, project, registerGuard, initialTaskId, onSelectionClose, onFocus }) {
  const [board, setBoard] = useState(null), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [view, setView] = useState('board'), [search, setSearch] = useState(''), [priority, setPriority] = useState(''), [status, setStatus] = useState(''), [sort, setSort] = useState('position');
  const [adding, setAdding] = useState(null), [selected, setSelected] = useState(initialTaskId || null), [columnDialog, setColumnDialog] = useState(null), [announcement, setAnnouncement] = useState('');
  useEffect(()=>{if(initialTaskId)setSelected(initialTaskId);},[initialTaskId]);
  const request = useRef(0), working = useRef(false), detailGuard = useRef(() => true);
  const registerDetailGuard = useCallback(guard => { detailGuard.current = guard; return () => { if (detailGuard.current === guard) detailGuard.current = () => true; }; }, []);
  const refresh = useCallback(async () => {
    const sequence = ++request.current;
    const result = await loadBoard(api, project.id);
    if (sequence === request.current) setBoard(result);
  }, [api, project.id]);
  useEffect(() => {
    setLoading(true);
    refresh().catch(e => setError(e.message)).finally(() => setLoading(false));
    return () => { request.current++; };
  }, [refresh]);
  useEffect(() => registerGuard(() => !working.current && detailGuard.current()), [registerGuard]);
  async function run(path, method, data) {
    if (working.current) throw new Error('Wait for the current save to finish.');
    working.current = true; setBusy(true); setError('');
    try {
      const result = await api(path, { method, ...jsonBody(data) });
      try { await refresh(); } catch (e) { setBoard(null); setError(`Saved, but the board could not refresh. ${e.message}`); }
      setAnnouncement('Changes saved.');
      return result;
    } catch (e) {
      setError(e.message);
      if (e.status === 409) { try { await refresh(); } catch { /* keep the conflict message */ } }
      throw e;
    } finally { working.current = false; setBusy(false); }
  }
  const filtered = search.trim() || priority || status || sort !== 'position';
  const visible = board ? visibleTasks(board.tasks, { search, priority, status, sort }) : [];
  const cannotMove = busy || project.archived || !board;
  async function drop(type, id, target, explicit = false) {
    if (cannotMove || (filtered && type === 'task' && !explicit)) return;
    try {
      await run(`/projects/${project.id}/${type === 'column' ? 'columns' : 'tasks'}/${id}/move`, 'POST', {
        board_revision: board.revision, before_id: target.before_id, ...(type === 'task' ? { column_id: target.column_id } : {}),
      });
      setAnnouncement(`${type === 'task' ? 'Task' : 'Column'} moved and saved.`);
      requestAnimationFrame(() => document.querySelector(`[data-grip="${type}-${id}"]`)?.focus());
    } catch { /* error is displayed by run */ }
  }
  const { drag, start } = useBoardDrag(drop, cannotMove);
  function keyMove(event, type, row) {
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key) || cannotMove || (type === 'task' && filtered)) return;
    event.preventDefault();
    const index = board.columns.findIndex(c => c.id === (type === 'task' ? row.column_id : row.id));
    if (type === 'column') {
      if (event.key === 'ArrowLeft' && index > 0) drop(type, row.id, { before_id: board.columns[index - 1].id });
      if (event.key === 'ArrowRight' && index < board.columns.length - 1) drop(type, row.id, { before_id: board.columns[index + 2]?.id ?? null });
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      const destination = board.columns[index + (event.key === 'ArrowLeft' ? -1 : 1)];
      if (destination) drop(type, row.id, { column_id: destination.id, before_id: null });
    } else {
      const before = taskMove(board.tasks, row, row.column_id, event.key === 'ArrowUp' ? 'up' : 'down');
      if (before !== undefined) drop(type, row.id, { column_id: row.column_id, before_id: before });
    }
  }
  async function retry() { setLoading(true); setError(''); try { await refresh(); } catch (e) { setError(e.message); } finally { setLoading(false); } }
  const task = board?.tasks.find(t => t.id === selected);
  return <div className="ws-tasks"><div className="ws-section-heading"><div><h2>Tasks</h2><p className="muted">A small step today. A little more progress tomorrow.</p></div><button className="primary compact" disabled={cannotMove} onClick={() => setAdding({ columnId: board.columns[0].id })}>+ New task</button></div>
    <div className="ws-toolbar"><div className="ws-segment" aria-label="Task view"><button aria-pressed={view === 'board'} onClick={() => setView('board')}>Board</button><button aria-pressed={view === 'list'} onClick={() => setView('list')}>List</button></div>
      <input type="search" aria-label="Search tasks" placeholder="Search tasks…" value={search} onChange={e => setSearch(e.target.value)} />
      <select aria-label="Filter task priority" value={priority} onChange={e => setPriority(e.target.value)}><option value="">All priorities</option>{priorities.map(p => <option key={p}>{p}</option>)}</select>
      <select aria-label="Filter task status" value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option>{board?.columns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      <select aria-label="Sort tasks" value={sort} onChange={e => setSort(e.target.value)}><option value="position">Board order</option><option value="due">Due date</option><option value="priority">Priority</option><option value="title">Title</option><option value="updated">Recently updated</option></select>
      <button className="secondary" disabled={busy} onClick={retry}>Refresh</button></div>
    <ErrorNotice error={error} retry={retry} />
    <p className="ws-board-hint" id="board-keyboard-hint">{filtered ? 'Filtered or sorted view. Clear filters and choose Board order to drag tasks.' : 'Drag the grip to move. On a focused grip, use arrow keys to move tasks or columns. Changes save immediately.'}</p>
    <span className="ws-sr-only" role="status" aria-live="polite">{announcement}</span>
    {loading && <p className="ws-loading" role="status">Loading task board…</p>}
    {board && view === 'board' && <div className="ws-board" aria-label="Task board">{board.columns.map((column, index) => {
      const items = visible.filter(t => t.column_id === column.id);
      return <section data-column-zone={column.id} key={column.id} className={`ws-column ${drag?.target?.column_id === column.id ? 'drop-target' : ''} ${drag?.type === 'column' && drag.id === column.id ? 'drag-source' : ''}`} aria-label={`${column.name} column`}>
        <header><button className="ws-grip" data-grip={`column-${column.id}`} aria-label={`Move column ${column.name}`} aria-describedby="board-keyboard-hint" disabled={cannotMove}
          onPointerDown={e => start(e, 'column', column)} onKeyDown={e => keyMove(e, 'column', column)}>⠿</button><span className={`ws-status-dot ${column.is_done ? 'done' : `status-${index}`}`} /><h3>{column.name}</h3><span className="ws-count">{items.length}</span>
          <button className="icon" aria-label={`Edit column ${column.name}`} disabled={cannotMove} onClick={() => setColumnDialog(column)}>···</button></header>
        <div className="ws-column-tasks">{items.map(item => <div data-task-card={item.id} key={item.id} className={`ws-task-card ${drag?.id === item.id && drag.type === 'task' ? 'drag-source' : ''} ${drag?.target?.before_id === item.id ? 'drop-before' : ''}`}>
          <div className="ws-task-card-top"><button className="ws-grip" data-grip={`task-${item.id}`} aria-label={`Move task ${item.title}`} aria-describedby="board-keyboard-hint" disabled={cannotMove || !!filtered} onPointerDown={e => start(e, 'task', item)} onKeyDown={e => keyMove(e, 'task', item)}>⠿</button>
            <button className="ws-task-title" onClick={() => setSelected(item.id)}>{item.title}</button></div>
          {item.description && <p>{item.description}</p>}<TaskBadge task={item} />
          {item.subtask_count > 0 && <small className="ws-subtask-count">{item.completed_subtasks}/{item.subtask_count} subtasks</small>}
        </div>)}
          {!items.length && <p className="ws-column-empty">{filtered ? 'No matching tasks' : 'A little room for what’s next'}</p>}
          <button className="ws-add-card" disabled={cannotMove} onClick={() => setAdding({ columnId: column.id })}>+ Add task</button></div>
      </section>;
    })}<button className="ws-add-column" disabled={cannotMove || board.columns.length >= 40} onClick={() => setColumnDialog({ new: true })}>+ Add column</button></div>}
    {board && view === 'list' && <div className="ws-task-list">{visible.map(item => <div className="ws-task-list-row" key={item.id}>
      <button className="ws-task-title" onClick={() => setSelected(item.id)}>{item.title}<TaskBadge task={item} /></button>
      <select aria-label={`Status for ${item.title}`} disabled={cannotMove} value={item.column_id} onChange={e => drop('task', item.id, { column_id: Number(e.target.value), before_id: null }, true)}>
        {board.columns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
    </div>)}{!visible.length && <Empty title="No tasks to show">Create a task or try different filters.</Empty>}</div>}
    {drag?.active && <div className="ws-drag-ghost" style={{ left: drag.x + 12, top: drag.y + 12 }} aria-hidden="true">{drag.title}</div>}
    {adding && board && <TaskCreate api={api} project={project} board={board} initial={adding} run={run} onClose={() => setAdding(null)} />}
    {task && <TaskDetails onFocus={onFocus} registerDetailGuard={registerDetailGuard} api={api} key={task.id} task={task} board={board} project={project} run={run} onClose={() => { setSelected(null); onSelectionClose?.(); }} onOpen={setSelected} />}
    {columnDialog && board && <ColumnDialog column={columnDialog} board={board} project={project} run={run} onClose={() => setColumnDialog(null)} />}
  </div>;
}

function TaskCreate({ project, board, initial, run, onClose }) {
  const [title, setTitle] = useState(''), [columnId, setColumnId] = useState(initial.columnId);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function save(e) { e.preventDefault(); if (busy) return; setBusy(true); setError('');
    try { await run(`/projects/${project.id}/tasks`, 'POST', { title, column_id: Number(columnId) }); onClose(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Modal title="New task" onClose={onClose} busy={busy}><form className="ws-form" onSubmit={save}><ErrorNotice error={error} /><label>Task title<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="What’s the next small step?" /></label><label>Status<select value={columnId} onChange={e => setColumnId(e.target.value)}>{board.columns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><div className="ws-form-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button><button className="primary compact" disabled={busy || !title.trim()}>{busy ? 'Creating…' : 'Create task'}</button></div></form></Modal>;
}

function ColumnDialog({ column, project, board, run, onClose }) {
  const [deleting, setDeleting] = useState(false), [destination, setDestination] = useState('');
  async function remove() { if (busy) return; setBusy(true); setError(''); try { await run(`/projects/${project.id}/columns/${column.id}`, 'DELETE', { board_revision: board.revision, destination_id: destination ? Number(destination) : null }); onClose(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  const [name, setName] = useState(column.name || ''), [done, setDone] = useState(!!column.is_done), [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function save(e) { e.preventDefault(); if (busy) return; setBusy(true); setError('');
    try { await run(`/projects/${project.id}/columns${column.new ? '' : `/${column.id}`}`, column.new ? 'POST' : 'PATCH', { name, is_done: done, board_revision: board.revision }); onClose(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Modal title={column.new ? 'New column' : deleting ? 'Delete column' : 'Edit column'} onClose={onClose} busy={busy}><form className="ws-form" onSubmit={e => { if (deleting) { e.preventDefault(); remove(); } else save(e); }}><ErrorNotice error={error} />
    {deleting ? <><p>Move this column’s tasks to another column before deleting it. Task content and attachments are preserved.</p><label>Move tasks to<select aria-label="Destination column" value={destination} onChange={e => setDestination(e.target.value)}><option value="">Choose a column</option>{board.columns.filter(c => c.id !== column.id).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><div className="ws-form-actions"><button type="button" className="secondary" disabled={busy} onClick={() => setDeleting(false)}>Cancel</button><button className="secondary danger" disabled={busy || (board.tasks.some(t => t.column_id === column.id) && !destination)}>Delete column</button></div></> : <><label>Column name<input required maxLength={80} value={name} onChange={e => setName(e.target.value)} /></label><label className="ws-checkbox"><input type="checkbox" checked={done} onChange={e => setDone(e.target.checked)} /> Tasks in this column count as complete</label><p className="muted">Changing this setting updates every task in the column.</p><div className="ws-form-actions">{!column.new && <button type="button" className="secondary danger" disabled={busy || board.columns.length <= 1} onClick={() => setDeleting(true)}>Delete column…</button>}<button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button><button className="primary compact" disabled={busy || !name.trim()}>{busy ? 'Saving…' : 'Save column'}</button></div></>}
  </form></Modal>;
}

function taskDraft(task) { return { title: task.title, description: task.description, priority: task.priority, due_date: task.due_date || '', document_ids: task.document_ids || [], checklist: task.checklist.map(({ text, completed }) => ({ text, completed })) }; }
function TaskDetails({ api, task, board, project, run, onClose, onOpen, registerDetailGuard, onFocus }) {
  const [uploadBusy, setUploadBusy] = useState(false);
  const [baseline, setBaseline] = useState(task), [draft, setDraft] = useState(() => taskDraft(task));
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [deleting, setDeleting] = useState(false), [subtask, setSubtask] = useState('');
  const dirty = JSON.stringify(draft) !== JSON.stringify(taskDraft(baseline));
  useEffect(() => {
    const before = event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', before);
    return () => window.removeEventListener('beforeunload', before);
  }, [dirty]);
  useEffect(() => registerDetailGuard(() => !busy && !uploadBusy && (!dirty || window.confirm('Discard unsaved task changes?'))), [registerDetailGuard, busy, uploadBusy, dirty]);
  const readonly = project.archived;
  const close = () => { if (uploadBusy) return; if (!dirty || window.confirm('Discard unsaved task changes?')) onClose(); };
  function field(key) { return { value: draft[key], onChange: e => setDraft({ ...draft, [key]: e.target.value }) }; }
  function item(index, values) { setDraft({ ...draft, checklist: draft.checklist.map((entry, i) => i === index ? { ...entry, ...values } : entry) }); }
  async function perform(action) {
    if (busy) return; setBusy(true); setError('');
    try { await action(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function save(event) {
    event.preventDefault();
    await perform(async () => {
      const result = await run(`/projects/${project.id}/tasks/${task.id}`, 'PATCH', { ...draft, due_date: draft.due_date || null, revision: baseline.revision });
      setBaseline(result.task); setDraft(taskDraft(result.task));
    });
  }
  async function move(row, columnId) {
    await perform(async () => {
      const result = await run(`/projects/${project.id}/tasks/${row.id}/move`, 'POST', { column_id: Number(columnId), before_id: null, board_revision: board.revision });
      if (row.id === task.id) setBaseline(previous => ({ ...previous, revision: result.task.revision, column_id: result.task.column_id, completed: result.task.completed }));
    });
  }
  const children = board.tasks.filter(t => t.parent_id === task.id).sort((a, b) => a.position - b.position);
  return <Modal title={deleting ? 'Delete task' : 'Task details'} onClose={close} busy={busy || uploadBusy} drawer><div className="ws-task-details"><ErrorNotice error={error} />
    {deleting ? <div className="ws-form"><p>Delete “{task.title}” and its subtasks? This cannot be undone.</p><div className="ws-form-actions"><button className="secondary" disabled={busy} onClick={() => setDeleting(false)}>Cancel</button><button className="secondary danger" disabled={busy} onClick={() => perform(async () => { await run(`/projects/${project.id}/tasks/${task.id}`, 'DELETE', { revision: baseline.revision }); onClose(); })}>Delete task</button></div></div> : <>
    <div className="ws-task-status">{onFocus&&<button className="primary compact" disabled={busy||uploadBusy||readonly} onClick={()=>{if(!dirty||window.confirm('Discard unsaved task edits and open Focus?'))onFocus(task.id);}}>Focus on this task</button>}<label>Status · saves immediately<select aria-label="Task status" value={task.column_id} disabled={busy || readonly} onChange={e => move(task, e.target.value)}>{board.columns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><span>{task.completion_percentage}% complete</span></div>
    <form className="ws-form" onSubmit={save}><label>Task title<input required maxLength={200} disabled={busy || readonly} {...field('title')} /></label><label>Description<textarea rows={4} maxLength={20000} disabled={busy || readonly} {...field('description')} /></label>
      <div className="ws-form-row"><label>Priority<select disabled={busy || readonly} {...field('priority')}>{priorities.map(p => <option key={p}>{p}</option>)}</select></label><label>Due date<input type="date" disabled={busy || readonly} {...field('due_date')} /></label></div>
      <div className="ws-checklist"><h3>Checklist</h3>{draft.checklist.map((entry, index) => <div key={index}><input type="checkbox" aria-label={`Complete checklist item ${index + 1}`} checked={entry.completed} disabled={busy || readonly} onChange={e => item(index, { completed: e.target.checked })} /><input aria-label={`Checklist item ${index + 1}`} required maxLength={300} value={entry.text} disabled={busy || readonly} onChange={e => item(index, { text: e.target.value })} /><button type="button" className="icon" aria-label={`Remove checklist item ${index + 1}`} disabled={busy || readonly} onClick={() => setDraft({ ...draft, checklist: draft.checklist.filter((_, i) => i !== index) })}>×</button></div>)}
        <button type="button" className="ws-text-button" disabled={busy || readonly || draft.checklist.length >= 100} onClick={() => setDraft({ ...draft, checklist: [...draft.checklist, { text: '', completed: false }] })}>+ Add checklist item</button></div>
      <TaskDocuments onBusy={setUploadBusy} api={api} project={project} ids={draft.document_ids} onChange={document_ids => setDraft(previous => ({ ...previous, document_ids }))} disabled={busy || readonly} />
      <div className="ws-form-actions"><span className="muted" role="status">{dirty ? 'Unsaved changes' : 'Saved'}</span><button type="button" className="secondary danger" disabled={busy || readonly} onClick={() => setDeleting(true)}>Delete…</button><button className="primary compact" disabled={busy || uploadBusy || readonly || !dirty || !draft.title.trim()}>{busy ? 'Saving…' : 'Save task'}</button></div>
      {error && <button type="button" className="secondary" onClick={() => { if (!dirty || window.confirm('Discard edits and reload the saved task?')) { setBaseline(task); setDraft(taskDraft(task)); setError(''); } }}>Reload saved version…</button>}
    </form>
    {!task.parent_id && <section className="ws-subtasks"><h3>Subtasks</h3>{children.map(child => <div key={child.id}><button className="ws-task-title" disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard unsaved task changes?')) onOpen(child.id); }}>{child.title}</button><select aria-label={`Status for subtask ${child.title}`} value={child.column_id} disabled={busy || readonly} onChange={e => move(child, e.target.value)}>{board.columns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select><button className="icon" aria-label={`Delete subtask ${child.title}`} disabled={busy || readonly} onClick={() => { if (window.confirm(`Delete subtask “${child.title}”?`)) perform(() => run(`/projects/${project.id}/tasks/${child.id}`, 'DELETE', { revision: child.revision })); }}>×</button></div>)}
      <form onSubmit={event => { event.preventDefault(); perform(async () => { await run(`/projects/${project.id}/tasks`, 'POST', { title: subtask, column_id: task.column_id, parent_id: task.id }); setSubtask(''); }); }}><input aria-label="New subtask title" placeholder="Add a small step…" required maxLength={200} value={subtask} disabled={busy || readonly} onChange={e => setSubtask(e.target.value)} /><button className="secondary" disabled={busy || readonly || !subtask.trim()}>Add subtask</button></form></section>}
    <p className="muted ws-task-date">Created {new Date(task.created_at).toLocaleDateString()} · Updated {new Date(task.updated_at).toLocaleDateString()}</p>
    </>}
  </div></Modal>;
}
