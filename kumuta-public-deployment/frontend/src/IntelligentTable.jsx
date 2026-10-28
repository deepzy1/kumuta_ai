import React,{useEffect,useRef,useState} from 'react';
import {aggregates,csvData,formatCell,scopedRows,tableRows,tableState} from './intelligentUI.js';
import {download,registerExport} from './componentExport.js';
import IntelligentChart from './IntelligentChart.jsx';
import Modal from './Modal.jsx';

export default function IntelligentTable({block,value,onValue,onAction,onInsert}) {
  const [local,setLocal]=useState(''),[scope,setScope]=useState('selected'),[metric,setMetric]=useState('sum');
  const root=useRef(null),state=tableState(value===undefined?local:value);
  const [chart,setChart]=useState(null),[chartError,setChartError]=useState('');
  const [chartColumn,setChartColumn]=useState('');
  const update=patch=>{const next={...state,...patch};if(onValue)onValue(next);else setLocal(next);};
  const filtered=tableRows(block,state),visible=scopedRows(block,state,'visible'),selected=scopedRows(block,state,'selected');
  const columns=block.columns.map((name,id)=>({name,id})).filter(c=>!state.hidden.includes(c.id));
  const scoped=scope==='selected'?selected:filtered,totals=aggregates(block,scoped);
  const pages=Math.max(1,Math.ceil(filtered.length/state.pageSize)),page=Math.min(state.page,pages-1),allChecked=visible.length>0&&visible.every(r=>state.selected.includes(r.id));
  useEffect(()=>registerExport(root.current,clone=>{
    const table=clone.querySelector('table'),body=table?.querySelector('tbody');if(!body)return;
    // Expand only at export time; the live table remains paginated.
    const template=body.querySelector('tr');body.replaceChildren();
    filtered.forEach(row=>{const tr=document.createElement('tr');const sample=template?.querySelectorAll('td');columns.forEach(({id},index)=>{const td=document.createElement('td');td.style.cssText=sample?.[index+1]?.style.cssText||'padding:8px;border-bottom:1px solid #ddd;font:12px system-ui;color:#111;';td.style.height='auto';const text=formatCell(row.cells[id],block.formats?.[id]);if(block.formats?.[id]?.kind==='status'){const badge=document.createElement('span');badge.textContent=text;const positive=/^(done|won|paid|complete|active)$/i.test(text),negative=/^(lost|overdue|failed|blocked)$/i.test(text);Object.assign(badge.style,{display:'inline-block',padding:'2px 8px',borderRadius:'20px',fontSize:'11px',fontWeight:'600',color:positive?'#065f46':negative?'#9f1239':'#334155',background:positive?'#d1fae5':negative?'#ffe4e6':'#e2e8f0'});td.appendChild(badge);}else td.textContent=text;tr.appendChild(td);});body.appendChild(tr);});
    table.querySelectorAll('[data-row-select]').forEach(n=>n.remove());
    table.querySelectorAll('.qui-export-column-name').forEach(n=>n.style.display='inline');
    const count=clone.querySelector('.qui-table-count');if(count)count.textContent=`${filtered.length} filtered result rows exported · ${block.rows.length} result rows in component · ${selected.length} selected within filters`;
  }),[block,value,local]);
  const ask=action=>onAction?.({action,scope,block,rows:scoped.map(r=>r.cells),row_ids:scoped.map(r=>r.id),query:state.query,filters:state.filters});
  function exportRows(){download(new Blob([csvData(columns.map(c=>c.name),scoped.map(r=>columns.map(c=>r.cells[c.id])))],{type:'text/csv;charset=utf-8'}),'kumuta-'+scope+'-rows.csv');}
  function generateChart(){
    if(!totals.length||scoped.length>100){setChartError('Choose 1–100 rows with a complete numeric column.');return;}
    const numeric=[totals.find(t=>String(t.column)===chartColumn)||totals[0]],labelColumn=block.columns.findIndex((_,i)=>!totals.some(t=>t.column===i));
    const format=block.formats?.[numeric[0].column],unit=format?.kind==='currency'?format.currency||'USD':format?.kind==='percent'?'%':'';
    const next={type:'chart',title:`${block.title||'Table'} · ${scoped.length} ${scope} rows`.slice(0,300),kind:'bar',labels:scoped.map(r=>labelColumn>=0?String(r.cells[labelColumn]):`Row ${r.id+1}`),series:numeric.map(t=>({name:t.name,values:scoped.map(r=>Number(r.cells[t.column]))})),unit};
    setChart(next);setChartError('');
  }
  return <div ref={root} className="qui-filtered-table">
    <div className="qui-table-tools" data-export-exclude="true"><label>Filter displayed rows<input aria-label="Filter displayed rows" type="search" maxLength={120} value={state.query} onChange={e=>update({query:e.target.value,page:0})} /></label>
      <details><summary>Columns & filters</summary><div className="qui-column-controls">{block.columns.map((name,id)=><div key={id}><label><input type="checkbox" checked={!state.hidden.includes(id)} disabled={columns.length===1&&!state.hidden.includes(id)} onChange={()=>update({hidden:state.hidden.includes(id)?state.hidden.filter(c=>c!==id):[...state.hidden,id]})} />{name}</label><input type="search" aria-label={`Filter ${name}`} placeholder="Contains…" maxLength={120} value={state.filters[id]||''} onChange={e=>update({filters:{...state.filters,[id]:e.target.value},page:0})} /><label>Width<input type="range" aria-label={`Width ${name}`} min={64} max={600} value={state.widths[id]||160} onChange={e=>update({widths:{...state.widths,[id]:Number(e.target.value)}})} /></label></div>)}</div></details>
    </div>
    <small className="qui-table-count">{filtered.length} of {block.rows.length} displayed result rows · {selected.length} selected in filters · {visible.length} on this page · source calculations unchanged</small>
    <div className="table-scroll" tabIndex={0} role="region" aria-label={block.title?`${block.title} data`:'Data table'}><table>
      <thead><tr><th data-row-select="true" data-export-exclude="true"><input aria-label="Select this page" type="checkbox" checked={allChecked} disabled={!visible.length} onChange={()=>update({selected:allChecked?state.selected.filter(id=>!visible.some(r=>r.id===id)):[...new Set([...state.selected,...visible.map(r=>r.id)])]})} /></th>{columns.map(({name,id})=><th key={id} aria-sort={state.sort?.column===id?(state.sort.direction==='asc'?'ascending':'descending'):'none'} style={{minWidth:state.widths[id]||100,width:state.widths[id]}}><button type="button" aria-label={`Sort ${name}`} onClick={()=>update({sort:{column:id,direction:state.sort?.column===id&&state.sort.direction==='asc'?'desc':'asc'},page:0})}>{name} {state.sort?.column===id?(state.sort.direction==='asc'?'↑':'↓'):'↕'}</button><span className="qui-export-column-name">{name}</span></th>)}</tr></thead>
      <tbody>{visible.map(({cells,id})=><tr key={id} aria-selected={state.selected.includes(id)}><td data-row-select="true" data-export-exclude="true"><input aria-label={`Select row ${id+1}`} type="checkbox" checked={state.selected.includes(id)} onChange={()=>update({selected:state.selected.includes(id)?state.selected.filter(n=>n!==id):[...state.selected,id]})} /></td>{columns.map(({id:col})=><td key={col}>{block.formats?.[col]?.kind==='status'?<span className={`qui-status ${/^(done|won|paid|complete|active)$/i.test(String(cells[col]))?'positive':/^(lost|overdue|failed|blocked)$/i.test(String(cells[col]))?'negative':'neutral'}`}>{String(cells[col])}</span>:formatCell(cells[col],block.formats?.[col])}</td>)}</tr>)}</tbody>
    </table>{!filtered.length&&<p role="status" className="qui-empty">No matching rows. Adjust search or column filters.</p>}</div>
    <div className="qui-pagination" data-export-exclude="true"><button type="button" disabled={page===0} onClick={()=>update({page:page-1})}>Previous rows</button><span>Page {page+1} of {pages}</span><button type="button" disabled={page+1>=pages} onClick={()=>update({page:page+1})}>Next rows</button><label>Rows per page<select aria-label="Rows per page" value={state.pageSize} onChange={e=>update({pageSize:Number(e.target.value),page:0})}>{[10,25,50,100].map(n=><option key={n}>{n}</option>)}</select></label></div>
    <div className="qui-row-actions" data-export-exclude="true"><label>Action scope<select aria-label="Table action scope" value={scope} onChange={e=>setScope(e.target.value)}><option value="selected">Selected rows within filters ({selected.length})</option><option value="filtered">Filtered result rows ({filtered.length})</option></select></label>
      <button type="button" onClick={()=>update({selected:[]})} disabled={!state.selected.length}>Clear selection</button>
      <select aria-label="Aggregate" value={metric} onChange={e=>setMetric(e.target.value)}>{['sum','average','min','max','count'].map(m=><option key={m}>{m}</option>)}</select>
      <button type="button" disabled={!scoped.length} onClick={exportRows}>Export rows CSV</button>
      {totals.length>1&&<label>Chart value<select aria-label="Chart value column" value={chartColumn||totals[0].column} onChange={e=>setChartColumn(e.target.value)}>{totals.map(t=><option key={t.column} value={t.column}>{t.name}</option>)}</select></label>}
      <button type="button" disabled={!scoped.length} onClick={generateChart}>Generate chart</button>
      {onAction&&['summarize','explain','compare','ask'].map(action=><button type="button" key={action} disabled={!scoped.length} onClick={()=>ask(action)}>{({summarize:'Summarize rows',explain:'Explain rows',compare:'Compare records',ask:'Ask AI about rows'})[action]}</button>)}
    </div>
    {scoped.length>0&&<div className="qui-aggregates" aria-live="polite"><strong>{scoped.length} {scope} rows</strong>{totals.map(t=><span key={t.column}>{t.name} · {metric}: <b>{formatCell(t[metric],metric==='count'?{kind:'number',decimals:0}:block.formats?.[t.column]||{kind:'number'})}</b></span>)}{!totals.length&&<span>Count: {scoped.length} · no complete numeric columns in this scope</span>}</div>}
    {chartError&&<p role="status">{chartError}</p>}
    {chart&&<Modal title="Selected rows chart" wide onClose={()=>setChart(null)}><section className="qui-derived-chart quickui"><h4>{chart.title}</h4><IntelligentChart block={chart} /><p className="muted">Preview from the rows selected when Generate chart was pressed. Original table preserved.</p><div data-export-exclude="true">{onInsert&&<button type="button" onClick={()=>{onInsert({engine:'B',capabilities:['local-state'],payload:{version:1,title:chart.title,blocks:[chart]}});setChart(null);}}>Add chart to canvas</button>}<button type="button" onClick={()=>setChart(null)}>Reject chart preview</button></div></section></Modal>}
  </div>;
}
