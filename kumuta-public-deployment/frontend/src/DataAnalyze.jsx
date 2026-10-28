import React, { useEffect, useState } from 'react';
import { jsonBody } from './api';
import { ErrorNotice, Empty } from './Modal';
import { Field } from './ModeUI';
import DataTable from './DataTable';
import DataChart from './DataChart';
import { defaultSpec, parseSpecDraft, supportedCharts } from './dataAnalysis';

export function AnalysisControls({ spec, onChange, schema, disabled=false }) {
 const columns=schema?.columns||[],numeric=columns.filter(c=>['integer','decimal'].includes(c.type)),dates=columns.filter(c=>['date','datetime'].includes(c.type));
 const set=(key,value)=>onChange({...spec,[key]:value,offset:0});
 const updateMetric=(i,key,value)=>set('metrics',spec.metrics.map((m,n)=>n===i?{...m,[key]:value}:m));
 const [advanced,setAdvanced]=useState(false),[raw,setRaw]=useState(''),[invalid,setInvalid]=useState('');
 function operation(value){onChange({...defaultSpec(),sheet:spec.sheet,operation:value,chart:value==='aggregate'?'bar':'table',metrics:value==='aggregate'?defaultSpec().metrics:[],filters:spec.filters});}
 return <fieldset className="data-controls" disabled={disabled}><legend>Configure analysis</legend><div className="data-form-grid">
  <Field label="Operation"><select aria-label="Operation" value={spec.operation} onChange={e=>operation(e.target.value)}><option value="aggregate">Aggregate & compare</option><option value="rows">Filter & sort rows</option><option value="missing">Missing values</option><option value="describe">Descriptive statistics</option></select></Field>
  <Field label="Visualization"><select aria-label="Visualization" value={spec.chart} onChange={e=>set('chart',e.target.value)}>{['table','bar','line','area','pie','donut','kpi','scatter'].map(v=><option key={v}>{v}</option>)}</select></Field>
  {spec.operation==='aggregate' && <><Field label="Group by"><select aria-label="Group by" value={spec.group_by[0]?.column||''} onChange={e=>set('group_by',e.target.value?[{column:e.target.value,period:null}]:[])}><option value="">All matching rows</option>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select></Field>
  {dates.some(c=>c.name===spec.group_by[0]?.column) && <Field label="Date grouping"><select aria-label="Date grouping" value={spec.group_by[0]?.period||''} onChange={e=>set('group_by',[{...spec.group_by[0],period:e.target.value||null}])}><option value="">Exact value</option>{['day','week','month','year'].map(v=><option key={v}>{v}</option>)}</select></Field>}</>}
 </div>
 {spec.operation!=='aggregate' && <Field label="Selected columns (empty means all)"><select aria-label="Selected columns" multiple value={spec.columns} onChange={e=>set('columns',[...e.target.selectedOptions].map(o=>o.value))}>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select><small>Use Ctrl/Command to select up to 20 columns.</small></Field>}
 {spec.operation==='aggregate' && <div className="data-metrics">{spec.metrics.map((m,i)=><div className="data-form-grid" key={i}>
  <Field label={`Metric ${i+1}`}><select aria-label={`Metric ${i+1}`} value={m.op} onChange={e=>set('metrics',spec.metrics.map((v,n)=>n===i?{...v,op:e.target.value,column:e.target.value==='count'?null:(numeric[0]?.name||columns[0]?.name||null)}:v))}>{['count','sum','average','min','max','distinct_count'].map(v=><option key={v}>{v}</option>)}</select></Field>
  <Field label={`Metric ${i+1} column`}><select aria-label={`Metric ${i+1} column`} value={m.column||''} onChange={e=>updateMetric(i,'column',e.target.value||null)}>{m.op==='count' && <option value="">All rows</option>}{(['count','distinct_count'].includes(m.op)?columns:numeric).map(c=><option key={c.name}>{c.name}</option>)}</select></Field>
  <Field label={`Metric ${i+1} name`}><input required maxLength={60} pattern="[A-Za-z][A-Za-z0-9_ ]*" value={m.alias} onChange={e=>updateMetric(i,'alias',e.target.value)}/></Field>
  {spec.metrics.length>1 && <button type="button" className="secondary" onClick={()=>set('metrics',spec.metrics.filter((_,n)=>n!==i))}>Remove metric {i+1}</button>}
 </div>)}<button type="button" className="secondary" disabled={spec.metrics.length>=8} onClick={()=>set('metrics',[...spec.metrics,{op:'count',column:null,alias:`Count${spec.metrics.length+1}`}])}>+ Metric</button></div>}
 {spec.operation==='aggregate' && <details className="data-filter-panel"><summary>Derived metrics ({spec.derived.length})</summary>{spec.derived.map((m,i)=>{
 const update=(key,value)=>set('derived',spec.derived.map((v,n)=>n===i?{...v,[key]:value}:v));
 return <div className="data-form-grid" key={i}><Field label={`Derived ${i+1} operation`}><select value={m.op} onChange={e=>update('op',e.target.value)}><option value="ratio">Ratio</option><option value="difference">Difference</option></select></Field>{['numerator','denominator'].map(key=><Field key={key} label={`Derived ${i+1} ${key}`}><select value={m[key]} onChange={e=>update(key,e.target.value)}>{spec.metrics.map(v=><option key={v.alias}>{v.alias}</option>)}</select></Field>)}<Field label={`Derived ${i+1} name`}><input required maxLength={60} value={m.alias} onChange={e=>update('alias',e.target.value)}/></Field><Field label={`Derived ${i+1} scale`}><select value={m.scale||1} onChange={e=>update('scale',Number(e.target.value))}><option value={1}>Value</option><option value={100}>Percent</option></select></Field><button className="secondary" type="button" onClick={()=>set('derived',spec.derived.filter((_,n)=>n!==i))}>Remove derived {i+1}</button></div>;
 })}<button className="secondary" type="button" disabled={spec.derived.length>=4||!spec.metrics.length} onClick={()=>set('derived',[...spec.derived,{op:'ratio',numerator:spec.metrics[0].alias,denominator:spec.metrics[1]?.alias||spec.metrics[0].alias,alias:`Ratio${spec.derived.length+1}`,scale:1}])}>+ Derived metric</button></details>}
 <details className="data-filter-panel"><summary>Filters ({spec.filters.length})</summary>{spec.filters.map((f,i)=><div key={i} className="data-form-grid">
  <Field label={`Filter ${i+1} column`}><select aria-label={`Filter ${i+1} column`} value={f.column} onChange={e=>set('filters',spec.filters.map((v,n)=>n===i?{...v,column:e.target.value}:v))}>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select></Field>
  <Field label={`Filter ${i+1} operator`}><select aria-label={`Filter ${i+1} operator`} value={f.op} onChange={e=>set('filters',spec.filters.map((v,n)=>n===i?{...v,op:e.target.value,value:['is_missing','not_missing'].includes(e.target.value)?null:''}:v))}>{['eq','ne','gt','gte','lt','lte','contains','is_missing','not_missing'].map(v=><option key={v}>{v}</option>)}</select></Field>
  {!['is_missing','not_missing'].includes(f.op) && <Field label={`Filter ${i+1} value`}><input value={String(f.value??'')} maxLength={4000} onChange={e=>set('filters',spec.filters.map((v,n)=>n===i?{...v,value:e.target.value}:v))}/></Field>}
  <button type="button" className="secondary" onClick={()=>set('filters',spec.filters.filter((_,n)=>n!==i))}>Remove filter {i+1}</button>
 </div>)}<button type="button" className="secondary" disabled={!columns.length||spec.filters.length>=12} onClick={()=>set('filters',[...spec.filters,{column:columns[0].name,op:'eq',value:''}])}>+ Filter</button></details>
 <div className="data-form-grid"><Field label="Sort results by"><input list="data-result-columns" placeholder="Result column or metric name" value={spec.sort[0]?.column||''} onChange={e=>set('sort',e.target.value?[{column:e.target.value,descending:spec.sort[0]?.descending||false}]:[])}/><datalist id="data-result-columns">{[...columns.map(c=>c.name),...spec.metrics.map(m=>m.alias)].map((n,i)=><option key={i} value={n}/>)}</datalist></Field>
 <Field label="Sort direction"><select value={spec.sort[0]?.descending?'desc':'asc'} onChange={e=>spec.sort.length&&set('sort',[{...spec.sort[0],descending:e.target.value==='desc'}])}><option value="asc">Ascending / bottom N</option><option value="desc">Descending / top N</option></select></Field>
 <Field label="Result rows (N)"><input type="number" min={1} max={500} value={spec.limit} onChange={e=>set('limit',Number(e.target.value))}/></Field></div>
 <button type="button" className="data-text-button" onClick={()=>{setAdvanced(!advanced);setRaw(JSON.stringify(spec,null,2));setInvalid('');}}>Advanced specification {advanced?'↑':'↓'}</button>
 {advanced && <div><p className="muted">Declarative JSON only. Add two groups, selected columns, membership filters, multiple sorts or ratio/difference metrics here.</p><textarea aria-label="Analysis specification JSON" rows={12} value={raw} onChange={e=>setRaw(e.target.value)}/><ErrorNotice error={invalid}/><button type="button" className="secondary" onClick={()=>{try{const parsed=parseSpecDraft(raw);onChange(parsed);setInvalid('');setAdvanced(false);}catch(e){setInvalid(e.message);}}}>Apply specification</button></div>}
 </fieldset>;
}

export function AnalysisResult({result:original,title='Analysis results',onSave}) {
 const [chart,setChart]=useState(original.spec.chart);
 const result={...original,spec:{...original.spec,chart}};
 useEffect(()=>setChart(original.spec.chart),[original]);
 return <section className="data-card data-result"><div className="data-heading"><h3>{title}</h3>{onSave && <button type="button" className="primary compact" onClick={()=>onSave(result)}>Save to report</button>}</div><p>{result.answer}</p>
  <p className="data-usage">{result.gemini_used?`Gemini interpreted the request · ${result.model} · 1 generation`:'Local analysis · Zero Gemini calls'} · Calculations run locally</p>
  {onSave&&<Field label={`Chart type for ${title}`}><select value={chart} onChange={e=>setChart(e.target.value)}>{[...new Set([chart,...supportedCharts(result)])].map(c=><option key={c}>{c}</option>)}</select></Field>}<DataChart result={result} title={title}/>
  <DataTable caption="Computed results" columns={result.columns} rows={result.rows}/>
  <details><summary>Sources, filters & calculation details</summary><p>Dataset: {result.dataset.name} · Worksheet: {result.sheet} · Revision: {result.dataset.revision}</p><p>SHA-256: <code className="data-hash">{result.dataset.sha256}</code></p><p>{result.source_rows} source rows · {result.matched_rows} matched · {result.filtered_out} filtered out</p><p>{result.calculation}</p><pre>{JSON.stringify({columns:result.spec.columns,groups:result.spec.group_by,metrics:result.spec.metrics,derived:result.spec.derived,filters:result.spec.filters,missing_excluded:result.missing_excluded},null,2)}</pre></details>
  {result.warnings.map(w=><p className="data-warning" key={w}>{w}</p>)}
 </section>;
}

export default function DataAnalyze({api,base,datasets,initialId,registerGuard,onSave}) {
 const ready=datasets.filter(r=>r.status==='ready');
 const [did,setDid]=useState(initialId&&ready.some(r=>r.id===initialId)?initialId:ready[0]?.id||''),[spec,setSpec]=useState(defaultSpec),[schema,setSchema]=useState(null),[preview,setPreview]=useState(null),[result,setResult]=useState(null),[question,setQuestion]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [interpreted,setInterpreted]=useState(null),[advanced,setAdvanced]=useState(false),[schemaVersion,setSchemaVersion]=useState(0);
 const lock=React.useRef(false);
 const row=ready.find(r=>r.id===Number(did)),selectedSheet=spec.sheet||row?.sheets[0]?.name||'';
 useEffect(()=>{let alive=true;setSchema(null);setPreview(null);setResult(null);setInterpreted(null);setError('');if(!row)return;
 api(`${base}/datasets/${did}/preview?limit=10${spec.sheet?`&sheet=${encodeURIComponent(spec.sheet)}`:''}`).then(r=>{if(alive){setSchema(r);setPreview(r);}}).catch(e=>{if(alive)setError(e.message);});
 return()=>{alive=false;};},[api,base,did,selectedSheet,row?.revision,schemaVersion]);
 useEffect(()=>registerGuard?.(()=>!lock.current),[registerGuard]);
 function change(s){setSpec(s);setResult(null);setInterpreted(null);}
 async function run(ai=false,nextSpec=spec) {
  if(lock.current||!row)return;lock.current=true;setBusy(true);setError('');setResult(null);
  try {
   if(ai){setInterpreted(null);const output=await api(base+'/interpret',{method:'POST',...jsonBody({dataset_id:Number(did),sheet:spec.sheet,question})});setSpec(output.spec);setInterpreted(output);}
   else{const output=await api(`${base}/datasets/${did}/analyze`,{method:'POST',...jsonBody(nextSpec)});setResult({...output,...(interpreted?{gemini_used:true,model:interpreted.model}: {})});}
  }catch(e){setError(e.message);}finally{lock.current=false;setBusy(false);}
 }
 if(!ready.length)return <Empty title="Add data to start analyzing">Upload a CSV or Excel dataset to preview it and ask your first question. Processing is local.</Empty>;
 return <div className="data-analyze"><div className="data-card"><h3>Ask a question about your data</h3><ErrorNotice error={error} retry={()=>setSchemaVersion(v=>v+1)}/>
 <div className="data-form-grid"><Field label="Analysis dataset"><select disabled={busy} value={did} onChange={e=>{setDid(Number(e.target.value));change(defaultSpec());}}>{ready.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
 <Field label="Analysis worksheet"><select disabled={busy} value={spec.sheet||row?.sheets[0]?.name||''} onChange={e=>change({...defaultSpec(),sheet:e.target.value})}>{row?.sheets.map(s=><option key={s.name}>{s.name}</option>)}</select></Field></div>
 {preview&&<details className="data-preview"><summary>Preview {row.filename} · {preview.row_count.toLocaleString()} rows · {preview.column_count} columns</summary><DataTable caption="Dataset preview" columns={preview.columns.map(c=>c.name)} rows={preview.items}/><DataTable caption="Column types and missing values" columns={['Column','Type','Missing']} rows={preview.columns.map(c=>[c.name,c.type,c.missing])}/>{preview.warnings.map(w=><p className="data-warning" key={w}>{w}</p>)}</details>}
 <form onSubmit={e=>{e.preventDefault();run(true);}}><Field label="Ask about your data"><textarea disabled={busy} required maxLength={2000} value={question} onChange={e=>{setQuestion(e.target.value);setInterpreted(null);}} placeholder="What are the top 10 products by revenue?" rows={3}/></Field>
 <div className="data-question-examples">{['Compare monthly sales','Show category contribution as a pie chart','Which products have declining sales?'].map(q=><button type="button" key={q} disabled={busy} onClick={()=>{setQuestion(q);setInterpreted(null);}}>{q}</button>)}</div>
 <p className="muted">Your selected model receives only your question and column names/types. Dataset rows stay on your server. Calculations use the local engine.</p>
 <div className="data-actions"><button className="primary compact" disabled={busy||!schema||!question.trim()}>{busy?'Working…':'Interpret question · uses tokens'}</button><small>One generation, using your selected model and free/paid controls.</small></div></form>
 {interpreted&&<section className="data-intent-review" aria-label="Review interpreted analysis"><h4>Review interpreted analysis</h4><p role="status">{interpreted.explanation}</p><p>{spec.operation} · {spec.metrics.map(m=>`${m.op}(${m.column||'rows'}) as ${m.alias}`).join(', ')}{spec.group_by.length?` · Group by ${spec.group_by.map(g=>g.column+(g.period?` by ${g.period}`:'')).join(', ')}`:''} · {spec.chart} · Up to {spec.limit} rows</p><details><summary>Inspect filters and full specification</summary><pre>{JSON.stringify(spec,null,2)}</pre></details><button className="primary compact" disabled={busy} onClick={()=>run()}>Run reviewed analysis</button><button className="secondary" disabled={busy} onClick={()=>setAdvanced(true)}>Edit interpretation</button></section>}
 <details className="data-advanced" open={advanced} onToggle={e=>setAdvanced(e.currentTarget.open)}><summary>Advanced Analysis</summary><p>Configure calculations yourself. Local analysis uses zero AI calls.</p><form onSubmit={e=>{e.preventDefault();run();}}><AnalysisControls spec={spec} onChange={change} schema={schema} disabled={busy||!schema}/><button className="primary compact" disabled={busy||!schema}>{busy?'Analyzing…':'Run local analysis'}</button></form></details></div>
 {result&&<><AnalysisResult result={result} onSave={onSave}/>{result.has_more&&<button className="secondary" disabled={busy} onClick={()=>{const next={...result.spec,offset:result.spec.offset+result.spec.limit};setSpec(next);run(false,next);}}>Next result page</button>}</>}
 </div>;
}
