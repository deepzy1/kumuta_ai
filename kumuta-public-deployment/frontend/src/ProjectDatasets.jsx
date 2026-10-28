import React, { useEffect, useState } from 'react';
import { allPages } from './workspaceData';
import { ErrorNotice } from './Modal';
export default function ProjectDatasets({ api, projectId, onOpen }) {
  const [rows, setRows] = useState(null), [error, setError] = useState('');
  useEffect(() => { let alive = true; allPages(api, `/projects/${projectId}/data/datasets`).then(r => { if (alive) setRows(r); }).catch(e => { if (alive) setError(e.message); }); return () => { alive = false; }; }, [api, projectId]);
  return <section className="library-datasets"><div className="ws-section-heading"><div><h2>Spreadsheets &amp; datasets</h2><p className="muted">Project source files stored by Data Analysis.</p></div><button className="secondary" onClick={onOpen}>Open Data Analysis</button></div><ErrorNotice error={error} />{rows === null && !error && <p role="status">Loading datasets…</p>}{rows?.map(r => <button key={r.id} className="overview-row" onClick={()=>onOpen(r.id)}><span><strong>{r.name}</strong><small>{r.filename} · {Math.ceil(r.size / 1024)} KB · {r.status}</small></span><span>Analyze →</span></button>)}{rows?.length === 0 && <p className="muted">Upload a CSV or Excel file in Data Analysis.</p>}</section>;
}
