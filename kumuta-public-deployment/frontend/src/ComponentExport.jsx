import React,{useState} from 'react';
import {exportComponents} from './componentExport.js';
import Modal from './Modal.jsx';

export default function ComponentExport({items,compact=false}) {
  const [open,setOpen]=useState(false),[format,setFormat]=useState('png'),[scale,setScale]=useState(2),[archive,setArchive]=useState(false),[orientation,setOrientation]=useState('landscape'),[margin,setMargin]=useState(24),[pageNumbers,setPageNumbers]=useState(true),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  async function run(){setBusy(true);setMessage('');try{const result=await exportComponents(typeof items==='function'?items():items,{format,scale,archive,orientation,margin,pageNumbers});setMessage(`${result.exported} component${result.exported===1?'':'s'} exported${result.pages?` · ${result.pages} pages`:''}.${result.failures.length?' Some components failed: '+result.failures.join('; '):''}`);}catch(e){setMessage(e.message);}finally{setBusy(false);}}
  const count=compact?1:(typeof items==='function'?items():items)?.length||0;
  return <span className="component-export" data-export-exclude="true" onPointerDown={e=>e.stopPropagation()}>
    <button type="button" aria-label={compact?'Export component':'Export selected components'} disabled={!count} onClick={()=>{setOpen(true);setMessage('');}}>↧ Export{!compact&&count>1?` (${count})`:''}</button>
    {open&&<Modal busy={busy} title={count>1?'Export selected components':'Export component'} onClose={()=>{if(!busy)setOpen(false);}}><div className="component-export-options">
      <p>{count} component{count===1?'':'s'} · current filtered data and input state</p>
      <ol>{(typeof items==='function'?items():items).map((item,i)=><li key={i}>{item.title||`Component ${i+1}`}</li>)}</ol>
      <label>Format<select aria-label="Export format" value={format} onChange={e=>setFormat(e.target.value)}><option value="png">PNG</option><option value="jpeg">JPEG</option><option value="pdf">PDF · one component per page</option></select></label>
      <label>Resolution<select aria-label="Export resolution" value={scale} onChange={e=>setScale(Number(e.target.value))}>{[1,2,3].map(n=><option key={n} value={n}>{n}×</option>)}</select></label>
      {format==='pdf'&&<><label>Orientation<select value={orientation} onChange={e=>setOrientation(e.target.value)}><option value="landscape">Landscape</option><option value="portrait">Portrait</option></select></label><label>Margins<select value={margin} onChange={e=>setMargin(Number(e.target.value))}><option value={24}>Standard</option><option value={0}>None</option></select></label><label><input type="checkbox" checked={pageNumbers} onChange={e=>setPageNumbers(e.target.checked)} />Page numbers</label></>}
      <label><input type="checkbox" checked={archive} onChange={e=>setArchive(e.target.checked)} />ZIP · separate file for each component</label>
      <small>Filtered tables include every matching result row across pages. Document cards include the loaded page or excerpt. Tall content continues onto additional PDF pages. Multiple images download as ZIP. Raster PDF preserves appearance; text is not selectable.</small>
      <button type="button" className="primary" disabled={busy} onClick={run}>{busy?'Preparing export…':archive?'Download ZIP':`Download ${format.toUpperCase()}`}</button>
      {message&&<p role="status">{message}</p>}
    </div></Modal>}
  </span>;
}
