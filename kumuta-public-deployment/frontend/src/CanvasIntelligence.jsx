import React, {useEffect,useState} from 'react';
import {jsonBody} from './api.js';
import {resourceKey} from './canvasResources.js';
import {applicableActions,intelligenceReferences,intelligenceSelection} from './canvasIntelligence.js';
import './canvasIntelligence.css';

export default function CanvasIntelligence({api,board,revision,selection,prompt,value,onChange,resources,onResources,disabled,onResource,onProposal,active=true}) {
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[result,setResult]=useState(null),[manual,setManual]=useState(false),[specs,setSpecs]=useState({});
  useEffect(()=>{if(!active||(board.role&&board.role!=='owner'))return;const abort=new AbortController();api(`/boards/${board.id}/resource-library`,{signal:abort.signal}).then(r=>{if(!abort.signal.aborted)onResources(r.items);}).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();},[api,board.id,revision,active,selection?.id]);
  useEffect(()=>{setResult(null);setError('');},[value,prompt,selection]);
  const ready=resources.filter(r=>r.status==='ready'&&['document','dataset'].includes(r.kind));
  const refs=intelligenceReferences(value,resources,selection),chosen=ready.filter(r=>refs.some(x=>resourceKey(x)===resourceKey(r)));
  const actions=applicableActions(chosen),labels={ask:'Ask',search:'Search',summarize:'Summarize',compare:'Compare',analyze:'Analyze',visualize:'Visualize',report:'Create report'};
  function change(next){onChange({...value,confirmFull:false,analyses:[],...next});setResult(null);setError('');}
  function request(local=false){
    const request=intelligenceSelection(value,resources,selection,revision,prompt);
    if(!request)throw Error('Choose sources first.');
    if(local){request.intelligence.analyses=refs.filter(ref=>ref.kind==='dataset').map(ref=>{
      const r=chosen.find(r=>r.source_id===ref.source_id&&r.kind==='dataset');
      const s=specs[resourceKey(r)]||{},sheet=ref.sheet||r.sheets?.[0]?.name;
      return {source_id:r.source_id,spec:{sheet,operation:s.operation||'aggregate',
        ...((s.operation||'aggregate')==='aggregate'?{metrics:[{op:s.metric||'count',...(s.column?{column:s.column}:{}),alias:'Value'}],group_by:s.group?[{column:s.group,...(s.period?{period:s.period}:{})}]:[]}:{}),limit:100,chart:s.chart||'bar'}};
    });}
    return request;
  }
  async function run(action){setBusy(true);setError('');try{await action();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function calculate(){const response=await api(`/boards/${board.id}/intelligence/analyze`,{method:'POST',...jsonBody(request(true))});setResult(response);}
  async function preview(saveDataReport=false){const artifact=await api(`/boards/${board.id}/intelligence/proposals`,{method:'POST',...jsonBody({request_key:crypto.randomUUID(),selection:request(true),title:prompt.trim().slice(0,200)||'Verified analysis',save_data_report:saveDataReport})});onProposal(artifact);}
  if(board.role&&board.role!=='owner')return <p className="canvas-intelligence">Owner source files and fresh RAG evidence remain private. AI Select can use visible accepted board content.</p>;
  return <div className="canvas-intelligence" aria-label="Source intelligence">
    <label className="intelligence-scope">Sources<select aria-label="Source scope" disabled={disabled||busy} value={value.scope} onChange={e=>change({scope:e.target.value,operation:'ask',automatic:true,fullDocument:false,keys:e.target.value==='resource'?(selection?.request?.resources?.[0]?[resourceKey(selection.request.resources[0])]:value.keys.slice(0,1)):value.keys})}>
      <option value="selection">Selection</option><option value="resource">This resource</option><option value="selected">Selected resources</option><option value="board">Board resources</option>
    </select></label>
    {value.scope==='selection'?<small>{selection?'Selected canvas content only.':null}</small>:<>
      {value.scope==='resource'&&<select aria-label="Current source" disabled={disabled||busy} value={value.keys[0]||''} onChange={e=>change({keys:[e.target.value]})}><option value="">Choose a source…</option>{ready.map(r=><option key={resourceKey(r)} value={resourceKey(r)}>{r.filename}</option>)}</select>}
      {value.scope==='selected'&&<details><summary>Choose resources ({chosen.length})</summary><div className="intelligence-source-list">{ready.map(r=><label key={resourceKey(r)}><input type="checkbox" checked={value.keys.includes(resourceKey(r))} disabled={disabled||busy} onChange={e=>change({keys:e.target.checked?[...value.keys,resourceKey(r)]:value.keys.filter(k=>k!==resourceKey(r))})}/>{r.filename}</label>)}</div></details>}
      <small>{chosen.length?chosen.map(r=>r.filename).join(' · '):'No eligible sources chosen.'}{value.scope==='board'?' · All ready linked documents and datasets; images excluded.':''}</small>
      {chosen.filter(r=>r.kind==='dataset').map(r=><label key={resourceKey(r)}>Worksheet · {r.filename}<select aria-label={`Analysis worksheet ${r.filename}`} multiple={value.scope==='selected'} disabled={disabled||busy} value={value.scope==='selected'?(refs.filter(x=>resourceKey(x)===resourceKey(r)).map(x=>x.sheet||r.sheets?.[0]?.name)):(refs.find(x=>resourceKey(x)===resourceKey(r))?.sheet||r.sheets?.[0]?.name||'')} onChange={e=>{if(value.scope==='selected'&&!e.target.selectedOptions.length)return;change({sheets:{...value.sheets,[resourceKey(r)]:value.scope==='selected'?[...e.target.selectedOptions].map(o=>o.value):e.target.value}});}}>{r.sheets?.map(s=><option key={s.name}>{s.name}</option>)}</select></label>)}
      <div className="intelligence-actions">{actions.map(a=><button key={a} type="button" aria-pressed={value.operation===a} disabled={disabled||busy} onClick={()=>change({operation:a,automatic:false,fullDocument:false})}>{labels[a]}</button>)}</div>
      {['summarize','compare','report'].includes(value.operation)&&chosen.some(r=>r.kind==='document')&&<label><input type="checkbox" checked={value.fullDocument} disabled={disabled||busy} onChange={e=>change({fullDocument:e.target.checked})}/>Use complete extracted documents (bounded)</label>}
      {value.fullDocument&&chosen.filter(r=>r.kind==='document').length>1&&<label><input type="checkbox" checked={value.confirmFull} disabled={disabled||busy} onChange={e=>change({confirmFull:e.target.checked})}/>Confirm multi-document processing · one Gemini generation if within budget; larger sources require Documents hierarchical summary.</label>}
      <small>{['analyze','visualize'].includes(value.operation)?'Complete chosen worksheets; one Gemini specification call on Send, calculations run locally.':value.operation==='search'?'Search runs locally with zero Gemini calls.':value.fullDocument?'Full extracted-text coverage or a visible size limitation.':'Bounded lexical FTS5/BM25 evidence; semantic search is unavailable.'}</small>
      {value.operation==='search'&&<button type="button" disabled={disabled||busy||!prompt.trim()||!chosen.length} onClick={()=>run(async()=>setResult(await api(`/boards/${board.id}/intelligence/search`,{method:'POST',...jsonBody(request())})))}>Search passages locally</button>}
      {chosen.some(r=>r.kind==='dataset')&&<details open={manual} onToggle={e=>setManual(e.currentTarget.open)}><summary>Local calculation · no Gemini</summary>
        {chosen.filter(r=>r.kind==='dataset').map(r=>{const key=resourceKey(r),s=specs[key]||{},sheet=r.sheets?.find(x=>x.name===refs.find(x=>resourceKey(x)===key)?.sheet)||r.sheets?.[0],columns=sheet?.columns||[];function edit(field,val){setSpecs(old=>({...old,[key]:{...s,[field]:val}}));setResult(null);}return <fieldset key={key} disabled={disabled||busy}><legend>{r.filename}</legend>
          <label>Operation<select aria-label="Operation" value={s.operation||'aggregate'} onChange={e=>edit('operation',e.target.value)}><option value="aggregate">Aggregate</option><option value="missing">Missing values</option><option value="describe">Describe</option></select></label>
          <label>Metric<select aria-label="Metric" value={s.metric||'count'} onChange={e=>edit('metric',e.target.value)}>{['count','sum','average','min','max','distinct_count'].map(v=><option key={v}>{v}</option>)}</select></label>
          <label>Column<select aria-label="Column" value={s.column||''} onChange={e=>edit('column',e.target.value)}><option value="">Count rows</option>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label>
          <label>Group by<select aria-label="Group by" value={s.group||''} onChange={e=>edit('group',e.target.value)}><option value="">All rows</option>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label>
          <label>Date period<select aria-label="Date period" value={s.period||''} onChange={e=>edit('period',e.target.value)}><option value="">Exact value</option>{['day','week','month','quarter','year'].map(v=><option key={v}>{v}</option>)}</select></label>
          <label>Chart<select aria-label="Chart" value={s.chart||'bar'} onChange={e=>edit('chart',e.target.value)}>{['bar','line','table','kpi'].map(v=><option key={v}>{v}</option>)}</select></label>
        </fieldset>;})}
        <button type="button" disabled={disabled||busy||!!result?.context?.retrieval?.unavailable} onClick={()=>run(calculate)}>Calculate full worksheets</button>
        {result?.computed&&<div className="intelligence-actions"><button type="button" disabled={disabled||busy} onClick={()=>run(()=>preview())}>Preview verified widget</button><button type="button" disabled={disabled||busy||!board.project_id} onClick={()=>run(()=>preview(true))}>Save Data report & preview</button></div>}
      </details>}
      {result?.context&&<div className="intelligence-search-results" aria-label="Retrieved evidence"><small>{result.context.retrieval.coverage} · {result.context.retrieval.retrieval_ms} ms · {result.context.retrieval.context_bytes} bytes · 0 Gemini calls</small>{result.message&&<p>{result.message}</p>}{result.context.resources?.filter(r=>r.reference.kind==='document').map(r=><details key={r.canonical_id}><summary><button type="button" onClick={()=>onResource(r.reference)}>[{r.citation}] {r.label}</button></summary><p>{r.content.map(c=>c.text).join('\n')}</p></details>)}</div>}
      {value.analyses?.length>0&&<small>{value.analyses.length} verified calculation specifications will be recomputed locally on Send. <button type="button" disabled={disabled||busy} onClick={()=>onChange({...value,analyses:[]})}>Clear Send calculations</button></small>}
      {result?.computed&&<button type="button" disabled={disabled||busy} onClick={()=>onChange({...value,analyses:request(true).intelligence.analyses})}>Use calculations on Send</button>}
      {result?.computed?.results.map((r,i)=><div key={i} className="intelligence-computed"><strong>{r.answer}</strong><small>{r.coverage} · {r.matched_rows} matched rows · {result.computed.calculation_ms} ms</small>{r.warnings?.map((w,j)=><small key={j}>{w}</small>)}</div>)}
    </>}
    {busy&&<small role="status">Calculating locally…</small>}{error&&<p role="alert">{error}</p>}
  </div>;
}
