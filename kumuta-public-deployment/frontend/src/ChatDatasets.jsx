import React,{useEffect,useState} from 'react';
import {defaultSpec} from './dataAnalysis.js';

export default function ChatDatasets({api,cid,value,onChange,disabled,refresh}){
  const [rows,setRows]=useState([]),[error,setError]=useState('');
  useEffect(()=>{setError('');if(!cid){setRows([]);return;}const controller=new AbortController();api(`/conversations/${cid}/datasets`,{signal:controller.signal}).then(data=>setRows(data.items)).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[api,cid,refresh]);
  if(!rows.length&&!error)return null;
  function select(row,sheet,selected){
    const next=value.filter(v=>!(v.dataset_id===row.id&&v.sheet===sheet.name));
    if(selected){if(next.length>=4){setError('Choose up to four worksheets.');return;}next.push({dataset_id:row.id,sha256:row.sha256,sheet:sheet.name});}
    onChange(next);setError('');
  }
  function patch(item,change){onChange(value.map(v=>v===item?{...v,...change}:v));}
  return <details className="chat-datasets"><summary>Spreadsheet sources{value.length?` · ${value.length} selected`:''}</summary>
    <p>Choose worksheets to compare separately. Ask AI uses one accounted schema-only planning call per worksheet on Send; calculations run locally. Manual calculations need no planning call.</p>
    {rows.map(row=><div key={row.id}><strong>{row.filename}</strong>{row.status!=='ready'?<small> · {row.status}</small>:row.sheets.map(sheet=>{const item=value.find(v=>v.dataset_id===row.id&&v.sheet===sheet.name);const numeric=sheet.columns.filter(c=>['integer','decimal'].includes(c.type));return <div key={sheet.name} className="chat-sheet"><label><input type="checkbox" disabled={disabled} checked={!!item} onChange={e=>select(row,sheet,e.target.checked)}/>{sheet.name} · {sheet.row_count} rows</label>
      <small>Columns: {sheet.columns.map(c=>`${c.name} (${c.type})`).join(', ')}</small>
      {item&&<><label>Calculation<select aria-label={`Calculation for ${row.filename} ${sheet.name}`} disabled={disabled} value={item.spec?.metrics?.[0]?.op||'ai'} onChange={e=>{const op=e.target.value;patch(item,{spec:op==='ai'?null:{...defaultSpec(),sheet:sheet.name,metrics:[{op,column:op==='count'?null:numeric[0]?.name||null,alias:'Result'}]}});}}><option value="ai">Ask AI from message</option><option value="count">Count rows</option>{numeric.length>0&&<><option value="sum">Sum</option><option value="average">Average</option><option value="min">Minimum</option><option value="max">Maximum</option></>}</select></label>
      {item.spec&&<>{item.spec.metrics[0].op!=='count'&&<label>Value column<select disabled={disabled} value={item.spec.metrics[0].column} onChange={e=>patch(item,{spec:{...item.spec,metrics:[{...item.spec.metrics[0],column:e.target.value}]}})}>{numeric.map(c=><option key={c.name}>{c.name}</option>)}</select></label>}
      <label>Group by<select disabled={disabled} value={item.spec.group_by[0]?.column||''} onChange={e=>patch(item,{spec:{...item.spec,group_by:e.target.value?[{column:e.target.value}]:[]}})}><option value="">All rows</option>{sheet.columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label>
      {item.spec.group_by.length>0&&<label>Date period<select disabled={disabled} value={item.spec.group_by[0].period||''} onChange={e=>patch(item,{spec:{...item.spec,group_by:[{...item.spec.group_by[0],period:e.target.value||null}]}})}>{['','day','week','month','quarter','year'].map(p=><option key={p} value={p}>{p||'Exact values'}</option>)}</select></label>}
      <label>Display<select disabled={disabled} value={item.spec.chart} onChange={e=>patch(item,{spec:{...item.spec,chart:e.target.value}})}>{['table','bar','line','kpi'].map(v=><option key={v}>{v}</option>)}</select></label></>}
      </>}
    </div>;})}</div>)}{error&&<p role="alert">{error}</p>}
  </details>;
}
