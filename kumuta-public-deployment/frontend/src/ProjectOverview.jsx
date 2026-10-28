import React, { useEffect, useState } from 'react';
import { ListTodo, CheckCircle2, BookOpen, Timer, MessageSquare, ArrowUpRight } from 'lucide-react';
import { ErrorNotice } from './Modal';
import { reportQuery } from './analyticsData';

export default function ProjectOverview({ api, project, onTab, onNewChat, onReports }) {
  const [activity, setActivity] = useState([]);
  const [report, setReport] = useState(null), [error, setError] = useState(''), [preset, setPreset] = useState('7d'), [reload, setReload] = useState(0);
  useEffect(() => {
    let alive = true; setReport(null); setError('');
    const query = reportQuery({ preset, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, projectId: project.id });
    Promise.all([api(`/analytics?${query}`), api(`/projects/${project.id}/tasks?sort=updated&limit=5&roots_only=true`), api(`/projects/${project.id}/notes?limit=5`), api(`/conversations?project_id=${project.id}&limit=5`), api(`/focus/sessions?project_id=${project.id}&limit=5`), api(`/projects/${project.id}/study/lessons?completed=true&sort=updated&limit=5`)]).then(([r, tasks, notes, chats, sessions, lessons]) => { if (alive) { setReport(r); setActivity([...tasks.items.map(x => ({ ...x, tab: 'tasks', type: 'Task' })), ...notes.items.map(x => ({ ...x, tab: 'notes', type: 'Note' })), ...chats.items.map(x => ({ ...x, tab: 'chats', type: 'Conversation' })), ...sessions.items.filter(x=>x.ended_at).map(x=>({...x,title:x.status==='completed'?'Completed focus session':'Finished early focus session',updated_at:x.ended_at,tab:'focus',type:'Focus'})), ...lessons.items.filter(x=>x.completed).map(x=>({...x,updated_at:x.completed_at||x.updated_at,tab:'study',type:'Study progress'}))].sort((a,b) => b.updated_at.localeCompare(a.updated_at)).slice(0,5)); } }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [api, project.id, preset, reload]);
  const total = report?.workspace.tasks ?? project.overview?.tasks ?? 0;
  const done = report?.workspace.completed_tasks ?? project.overview?.completed_tasks ?? 0;
  const recent = [
    ...(report?.study.courses.items || []).map(x => ({ key: `c${x.id}`, title: x.title, detail: `${x.progress ?? 0}% complete`, tab: 'study' })),
    ...(report?.focus.sessions.items || []).slice(0, 4).map(x => ({ key: `s${x.id}`, title: 'Focus session', detail: new Date(x.ended_at).toLocaleString(), tab: 'focus' })),
  ];
  const points = report?.daily || [], max = Math.max(1, ...points.map(p => p.tasks + p.lessons + p.reviews));
  return <section className="project-overview">
    <div className="ws-section-heading"><div><h1>Project Overview</h1><p className="muted">{project.description || 'Your progress, activity and next steps.'}</p></div><select aria-label="Overview date range" value={preset} onChange={e => setPreset(e.target.value)}><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option></select></div>
    <ErrorNotice error={error} retry={() => setReload(n => n + 1)} />
    <div className="overview-stats">{[[ListTodo, total, 'Total tasks', 'tasks', 'green'], [CheckCircle2, done, 'Completed tasks', 'tasks', 'violet'], [MessageSquare, project.overview?.conversations ?? 0, 'Conversations', 'chats', 'blue'], [BookOpen, report?.study.lessons ?? '—', 'Study lessons', 'study', 'orange'], [Timer, report ? `${(report.focus.total_seconds / 3600).toFixed(1)} h` : '—', 'Focused time', 'focus', 'green']].map(([Icon, value, label, tab, color]) => <button key={label} onClick={() => onTab(tab)}><span className={`quick-icon ${color}`}><Icon size={20} /></span><strong>{value}</strong><span>{label}</span></button>)}</div>
    {!report && !error && <p role="status">Loading project activity…</p>}
    <div className="overview-grid">
      <section className="overview-card"><h2>Continue working</h2>{recent.slice(0, 5).map(row => <button className="overview-row" key={row.key} onClick={() => onTab(row.tab)}><span><strong>{row.title}</strong><small>{row.detail}</small></span><ArrowUpRight size={16} /></button>)}{!recent.length && <p className="muted">Start a course or a focus session to continue here.</p>}<button className="secondary" disabled={project.archived} onClick={onNewChat}>Start a project chat</button></section>
      <section className="overview-card"><h2>Task progress</h2><strong className="overview-progress-number">{total ? Math.round(done / total * 100) : 0}%</strong><progress aria-label="Completed tasks" value={done} max={total || 1} /><p className="muted">{done} of {total} tasks complete</p><h3>Completion activity</h3>{points.some(p => p.tasks + p.lessons + p.reviews) ? <div className="overview-chart" role="img" aria-label="Daily task, lesson and flashcard completions. Open detailed reports for values.">{points.map(p => <div key={p.date} title={`${p.date}: ${p.tasks} tasks, ${p.lessons} lessons, ${p.reviews} reviews`}><span style={{ height: `${(p.tasks + p.lessons + p.reviews) / max * 100}%` }} /><small>{p.date.slice(8)}</small></div>)}</div> : <p className="muted">Completed work will appear here.</p>}<button className="ws-text-button" onClick={onReports}>Detailed reports →</button></section>
      <section className="overview-card"><h2>Upcoming</h2>{report?.workspace.upcoming_tasks.items.slice(0, 6).map(x => <button className="overview-row" key={x.id} onClick={() => onTab('tasks')}><span><strong>{x.title}</strong><small>{x.due_date}</small></span><ListTodo size={16} /></button>)}{!report?.workspace.upcoming_tasks.items.length && <p className="muted">No upcoming tasks with due dates.</p>}<button className="ws-text-button" onClick={() => onTab('tasks')}>Open task board →</button></section>
    </div>
    {activity.length > 0 && <section className="overview-card overview-recent"><h2>Recent activity</h2><p className="muted">Recently updated project records</p>{activity.map(x => <button className="overview-row" key={`${x.tab}-${x.id}`} onClick={() => onTab(x.tab)}><span><strong>{x.type} · {x.title}</strong><small>{new Date(x.updated_at).toLocaleString()}</small></span><ArrowUpRight size={16} /></button>)}</section>}
    <div className="overview-actions">{[['tasks','Plan a task'], ['notes','Capture a note'], ['documents','Open documents'], ['data','Analyze data']].map(([tab, label]) => <button className="secondary" key={tab} onClick={() => onTab(tab)}>{label}<ArrowUpRight size={15} /></button>)}</div>
  </section>;
}
