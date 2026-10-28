import React, { useEffect, useState } from 'react';
import { useQuickUI } from './QuickUISettings.jsx';
import { CANVAS_DEFAULTS } from './canvasAppearance.js';

export default function CanvasAppearance() {
  const q=useQuickUI();
  const [draft,setDraft]=useState({...CANVAS_DEFAULTS,...q.preferences.canvas});
  const [revision,setRevision]=useState(q.revision),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false);
  useEffect(()=>{if(!dirty){setDraft({...CANVAS_DEFAULTS,...q.preferences.canvas});setRevision(q.revision);}},[q.revision,q.loaded,dirty]);
  const change=patch=>{setDraft(old=>({...old,...patch}));setDirty(true);setSaved(false);};
  async function save(){setBusy(true);setError('');try{await q.save({...q.preferences,canvas:draft},revision);setDirty(false);setSaved(true);}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <section className="canvas-appearance" aria-label="Canvas Appearance">
    <label>Appearance<select aria-label="Canvas appearance" value={draft.appearance} disabled={busy} onChange={e=>change({appearance:e.target.value,inherit:false})}>{['system','light','dark'].map(v=><option value={v} key={v}>{v[0].toUpperCase()+v.slice(1)}</option>)}</select></label>
    <label>Density<select aria-label="Canvas density" value={draft.density} disabled={busy} onChange={e=>change({density:e.target.value,inherit:false})}>{['comfortable','compact','spacious'].map(v=><option value={v} key={v}>{v[0].toUpperCase()+v.slice(1)}</option>)}</select></label>
    <section aria-label="Chart colors"><h3>Chart colors</h3><div className="canvas-chart-colors">{draft.chart_colors.map((color,i)=><label key={i}><span className="visually-hidden">Chart {i+1}</span><input aria-label={`Chart color ${i+1}`} type="color" disabled={busy} value={color} onChange={e=>change({inherit:false,chart_colors:draft.chart_colors.map((v,j)=>i===j?e.target.value:v)})} /></label>)}<button type="button" disabled={busy||draft.chart_colors.length>=8} onClick={()=>change({inherit:false,chart_colors:[...draft.chart_colors,'#16804a']})}>＋ Add</button></div>{draft.chart_colors.length>1&&<button className="settings-text-action" type="button" disabled={busy} onClick={()=>change({inherit:false,chart_colors:draft.chart_colors.slice(0,-1)})}>Remove last color</button>}</section>
    <details><summary>Theme options</summary><label className="canvas-inherit"><input type="checkbox" checked={draft.inherit} onChange={e=>change({inherit:e.target.checked})} /> Inherit Kumuta theme</label>
      <fieldset disabled={draft.inherit||busy}><label>Canvas accent<input aria-label="Canvas accent" type="color" value={draft.accent} onChange={e=>change({accent:e.target.value})} /></label>
      <label>Generated-widget palette<select aria-label="Widget palette mode" value={draft.widget_color.mode} onChange={e=>{const mode=e.target.value,colors=mode==='gradient'?['#16804a','#7c3aed']:[draft.widget_color.colors[0]];change({widget_color:{...draft.widget_color,mode,colors,stops:colors.map((_,i)=>i*100)}});}}><option value="system">Kumuta default</option><option value="solid">Solid</option><option value="gradient">Gradient</option></select></label>
      {draft.widget_color.colors.map((color,i)=><label key={i}>Widget color {i+1}<input aria-label={`Widget color ${i+1}`} type="color" value={color} disabled={draft.widget_color.mode==='system'} onChange={e=>change({widget_color:{...draft.widget_color,colors:draft.widget_color.colors.map((v,j)=>i===j?e.target.value:v)}})} /></label>)}</fieldset>
    </details>
    <button type="button" className="primary" disabled={busy||!q.loaded||!dirty} onClick={save}>Save changes</button>
    <button className="settings-text-action" type="button" disabled={busy} onClick={()=>{setDraft({...CANVAS_DEFAULTS,...q.preferences.canvas});setDirty(false);q.refresh();setError('');setSaved(false);}}>Reset to saved</button>
    {(error||q.error)&&<p role="alert">{error||q.error}</p>}{saved&&<p role="status">Canvas appearance saved.</p>}
  </section>;
}
