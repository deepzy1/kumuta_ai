import React, { useEffect, useState } from 'react';
import { reportQuery, metric, hours } from './analyticsData';
import './analytics.css';

type Props = {
  api: (path: string, options?: object) => Promise<any>;
  view?: 'study' | 'focus' | 'workspace';
  projectId?: number;
  workspaceId?: number;
};
type Point = { date: string; lessons: number; quiz_attempts: number; reviews: number; tasks: number; focus_seconds: number };
type Row = Record<string, any>;
type Page = { items: Row[]; has_more: boolean };
type Report = { study: Row; focus: Row; workspace: Row; daily: Point[]; weekly: Point[]; monthly: Point[]; range: Row; limitations: string[]; generated_at: string };

function Table({ title, columns, rows }: { title: string; columns: [string, string][]; rows: Row[] }) {
  return <section className="analytics-card"><h3>{title}</h3>{rows.length ? <div className="analytics-table"><table><caption className="sr-only">{title}</caption><thead><tr>{columns.map(([key, label]) => <th key={key} scope="col">{label}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={row.id ?? i}>{columns.map(([key]) => <td key={key}>{row[key] == null ? 'Unavailable' : String(row[key])}</td>)}</tr>)}</tbody></table></div> : <p className="muted">No records for this selection.</p>}</section>;
}

function Chart({ title, points, series }: { title: string; points: Point[]; series: [keyof Point, string][] }) {
  const max = Math.max(1, ...points.flatMap(p => series.map(([key]) => Number(p[key]))));
  const colors = ['#c2410c', '#1d4ed8', '#15803d'];
  return <section className="analytics-card"><h3>{title}</h3><div className="analytics-legend">{series.map(([key, label], i) => <span key={key}><i style={{ background: colors[i] }} />{label}</span>)}</div>
    <svg className="analytics-chart" viewBox="0 0 640 170" role="img" aria-label={`${title}. Exact values are in the data table below.`}>
      <text x="0" y="14">{Math.round(max)}</text><line x1="32" x2="628" y1="144" y2="144" stroke="#d6d3d1" />
      {series.map(([key, label], i) => <g key={key}><title>{label}</title>{points.map((p, n) => {
        const width = 592 / Math.max(1, points.length), bar = Math.max(.3, width / (series.length + 1));
        return <rect key={p.date} x={34 + n * width + i * bar} y={144 - Number(p[key]) / max * 116} width={bar} height={Number(p[key]) / max * 116} fill={colors[i]}><title>{p.date}: {p[key]}</title></rect>;
      })}</g>)}
      <text x="32" y="165">{points[0]?.date}</text><text x="628" y="165" textAnchor="end">{points.at(-1)?.date}</text>
    </svg>
    <details><summary>View activity data</summary><Table title={`${title} data`} columns={[['date', 'Date'], ...series.map(([key, label]) => [key, label] as [string, string])]} rows={points} /></details>
  </section>;
}

export default function Analytics({ api, view = 'workspace', projectId, workspaceId }: Props) {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  const [preset, setPreset] = useState('30d'), [start, setStart] = useState(''), [end, setEnd] = useState('');
  const [selectedProject, setSelectedProject] = useState(''), [courseId, setCourseId] = useState('');
  const [draftZone, setDraftZone] = useState(timezone), [zone, setZone] = useState(timezone);
  const [offset, setOffset] = useState(0), [grain, setGrain] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [data, setData] = useState<Report | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [exporting, setExporting] = useState(false), [refresh, setRefresh] = useState(0);
  const [projects, setProjects] = useState<Row[]>([]), [courses, setCourses] = useState<Row[]>([]);
  const pid = projectId || (selectedProject ? Number(selectedProject) : undefined);
  const valid = preset !== 'custom' || Boolean(start && end);
  const query = reportQuery({ preset, start, end, timezone: zone, projectId: pid, workspaceId, courseId: courseId ? Number(courseId) : undefined, offset });
  useEffect(() => {
    let alive = true;
    async function choices() {
      const items: Row[] = [];
      if (workspaceId && !projectId) {
        for (const archived of [false, true]) {
          let page = 0, more = true;
          while (more && alive) { const result = await api(`/workspaces/${workspaceId}/projects?archived=${archived}&limit=100&offset=${page}`); items.push(...result.items); more = result.has_more; page += 100; }
        }
        if (alive) setProjects(items);
      }
      const list: Row[] = [];
      if (pid) {
        let page = 0, more = true;
        while (more && alive) { const result = await api(`/projects/${pid}/study/courses?limit=200&offset=${page}`); list.push(...result.items); more = result.has_more; page += 200; }
      }
      if (alive) setCourses(list);
    }
    choices().catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [api, workspaceId, pid, projectId, refresh]);
  useEffect(() => {
    let alive = true; setData(null); setError('');
    if (!valid) { setBusy(false); return () => { alive = false; }; }
    setBusy(true);
    api(`/analytics?${query}`).then(result => { if (alive) setData(result); }).catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [api, query, valid, refresh]);
  useEffect(() => {
    const update = () => { if (document.visibilityState === 'visible') setRefresh(x => x + 1); };
    window.addEventListener('online', update); document.addEventListener('visibilitychange', update);
    return () => { window.removeEventListener('online', update); document.removeEventListener('visibilitychange', update); };
  }, []);
  function filter(setter: (value: string) => void, value: string) { setter(value); setOffset(0); }
  async function download() {
    setExporting(true); setError('');
    try {
      const blob = await api(`/analytics/export?${query}&kind=${view}`, { responseType: 'blob' });
      const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = `kumuta-${view}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : 'Export failed'); } finally { setExporting(false); }
  }
  const study = data?.study, focus = data?.focus, workspace = data?.workspace;
  const stats: [string, string][] = data ? view === 'study' ? [
    ['Course completion', metric(study!.completion_percentage, '%')], ['Lessons completed', `${study!.completed_lessons}/${study!.lessons}`],
    ['Quiz attempts', metric(study!.quiz_attempts)], ['Average quiz score', metric(study!.average_quiz_score, '%')],
    ['Flashcard reviews', metric(study!.flashcards_reviewed)], ['Cards due now', metric(study!.flashcards_due)],
    ['Review success (Good/Easy)', metric(study!.review_success_percentage, '%')], ['Streak at range end', metric(study!.streak_at_range_end, study!.streak_at_range_end === 1 ? ' day' : ' days')],
    ['Longest streak in range', metric(study!.longest_streak_in_range, study!.longest_streak_in_range === 1 ? ' day' : ' days')], ['Measured study time', hours(study!.study_seconds)],
    ['Completed planned time (this page)', `${study!.completed_planned_minutes_on_page} min`],
  ] : view === 'focus' ? [
    ['Focused time', hours(focus!.total_seconds)], ['Ended sessions', metric(focus!.session_count)], ['Average session', hours(focus!.average_session_seconds)],
    ['Completed tasks (current)', metric(workspace!.completed_tasks)], ['Task completions in range', metric(workspace!.tasks_completed_in_range)],
  ] : [['Project task progress', metric(workspace!.progress, '%')], ['Completed tasks', `${workspace!.completed_tasks}/${workspace!.tasks}`],
    ['Focused time', hours(focus!.total_seconds)], ['Lessons completed', `${study!.completed_lessons}/${study!.lessons}`]] : [];
  const pages: Page[] = data ? [study!.courses, study!.plans, study!.quiz_performance, focus!.goals, focus!.sessions, workspace!.projects, workspace!.upcoming_tasks] : [];
  return <section className="analytics" aria-label={`${view} analytics`}><div className="mode-heading"><div><span className="ws-eyebrow">YOUR PROGRESS</span><h2>{view === 'study' ? 'Study Dashboard' : view === 'focus' ? 'Focus Dashboard' : 'Workspace Overview'}</h2><p>Local reports from your saved activity.</p></div><button className="secondary" disabled={busy} onClick={() => setRefresh(x => x + 1)}>Refresh report</button></div>
    <div className="analytics-filters"><label>Date range<select value={preset} onChange={e => filter(setPreset, e.target.value)}><option value="today">Today</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="custom">Custom date range</option></select></label>
      {preset === 'custom' && <><label>Start date<input type="date" value={start} onChange={e => filter(setStart, e.target.value)} /></label><label>End date<input type="date" value={end} onChange={e => filter(setEnd, e.target.value)} /></label></>}
      <form onSubmit={e => { e.preventDefault(); filter(setZone, draftZone); }}><label>Report timezone<input value={draftZone} onChange={e => setDraftZone(e.target.value)} /></label><button className="secondary" type="submit">Apply timezone</button></form>
      {!projectId && workspaceId && <label>Report project<select value={selectedProject} onChange={e => { filter(setSelectedProject, e.target.value); setCourseId(''); }}><option value="">All projects</option>{projects.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>}
      {view !== 'focus' && pid && <label>Report course<select value={courseId} onChange={e => filter(setCourseId, e.target.value)}><option value="">All courses</option>{courses.map(x => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label>}
      <button className="secondary" onClick={download} disabled={!data || busy || exporting}>{exporting ? 'Exporting…' : 'Export CSV'}</button>
    </div>
    {error && <p role="alert" className="error">{error}</p>}{busy && <p role="status">Loading analytics…</p>}{!valid && <p>Select both dates to load a custom report (up to 366 days).</p>}
    {data && <><p className="muted">{data.range.start} – {data.range.end} · {data.range.timezone} · Updated {new Date(data.generated_at).toLocaleTimeString()}</p>
      <div className="analytics-stats">{stats.map(([label, value]) => <article className="analytics-card" key={label}><strong>{value}</strong><span>{label}</span></article>)}</div>
      <label className="analytics-grain">Activity grouping<select value={grain} onChange={e => setGrain(e.target.value as typeof grain)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
      {(view === 'study' || view === 'workspace') && <Chart title="Learning activity" points={data[grain]} series={[[ 'lessons', 'Lessons' ], ['quiz_attempts', 'Quiz attempts'], ['reviews', 'Reviews']]} />}
      {(view === 'focus' || view === 'workspace') && <><Chart title="Focused time (hours)" points={data[grain].map(x => ({ ...x, focus_seconds: Number((x.focus_seconds / 3600).toFixed(3)) }))} series={[[ 'focus_seconds', 'Hours' ]]} /><Chart title="Task completion trend" points={data[grain]} series={[[ 'tasks', 'Tasks' ]]} /></>}
      <div className="analytics-grid">{view !== 'focus' && <>
        <Table title="Course progress" columns={[[ 'title', 'Course' ], ['completed', 'Completed'], ['lessons', 'Lessons'], ['progress', 'Progress %']]} rows={study!.courses.items} />
        <Table title="Quiz performance by course" columns={[[ 'course_id', 'Course ID' ], ['attempts', 'Attempts'], ['average_score', 'Average %']]} rows={study!.quiz_performance.items} />
        <Table title="Flashcard review performance" columns={[[ 'rating', 'Rating' ], ['count', 'Reviews']]} rows={['Again', 'Hard', 'Good', 'Easy'].map((rating, i) => ({ rating, count: study!.review_ratings[String(i + 1)] }))} />
        <Table title="Learning goals and plans" columns={[[ 'title', 'Plan' ], ['progress', 'Progress %'], ['completed_milestones', 'Milestones done'], ['target_date', 'Target']]} rows={study!.plans.items} />
        <Table title="Upcoming study sessions (this page)" columns={[[ 'title', 'Session' ], ['starts_at', 'Starts' ], ['minutes', 'Planned minutes']]} rows={study!.upcoming_sessions_on_page} />
      </>}{view !== 'study' && <>
        <Table title="Project time distribution" columns={[[ 'name', 'Project' ], ['hours', 'Hours'], ['progress', 'Task progress %']]} rows={workspace!.projects.items.map((x: Row) => ({ ...x, hours: hours(x.focus_seconds) }))} />
        <Table title="Goal progress" columns={[[ 'title', 'Goal' ], ['progress', 'Progress %'], ['status', 'Status'], ['completed_milestones', 'Milestones done']]} rows={focus!.goals.items} />
        <Table title="Session history" columns={[[ 'kind', 'Kind' ], ['status', 'Status'], ['started_at', 'Started'], ['hours', 'Duration']]} rows={focus!.sessions.items.map((x: Row) => ({ ...x, hours: hours(x.elapsed_seconds) }))} />
        {focus!.active_session && <p>Active {focus!.active_session.status} session excluded from totals until ended.</p>}
      </>}
      <Table title="Relevant tasks" columns={[[ 'title', 'Task' ], ['due_date', 'Due date']]} rows={workspace!.upcoming_tasks.items} />
      <Table title="Completed milestones (current snapshot)" columns={[[ 'title', 'Milestone' ], ['parent', 'Goal / plan'], ['target_date', 'Target date']]} rows={workspace!.milestones_on_page.filter((x: Row) => x.completed)} />
      </div>
      <div className="analytics-pagination"><button className="secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous report page</button><span>Detail page {offset / 50 + 1} · totals cover all records</span><button className="secondary" disabled={!pages.some(x => x.has_more)} onClick={() => setOffset(offset + 50)}>Next report page</button></div>
      <details className="analytics-card"><summary>Metric definitions and data availability</summary><ul>{data.limitations.map(x => <li key={x}>{x}</li>)}</ul><p>Older completions with unknown dates: {study!.unknown_completion_dates} lessons, {workspace!.unknown_completion_dates} tasks. A zero is a known count; Unavailable means no measurement or denominator.</p></details>
    </>}
  </section>;
}
