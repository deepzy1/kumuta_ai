import React, { useRef, useState } from 'react';
import CanvasComposerPopover from './CanvasComposerPopover.jsx';

// Catalogue, eligibility and persistence all come from the shared Kumuta API.
export default function CanvasModelPicker({ catalogue, disabled, onSelect, onRefresh }) {
  const [search,setSearch]=useState('');
  const root=useRef(null);
  const selected=catalogue?.models.find(m=>m.id===catalogue.selected);
  function eligible(m){return m.tier==='free'||(m.tier==='paid'&&catalogue.allow_paid_models);}
  const rows=catalogue?.models.filter(m=>`${m.name} ${m.id} ${m.tier} ${m.provider||''}`.toLowerCase().includes(search.toLowerCase()))||[];
  return <div className="canvas-model-control" ref={root} onKeyDown={e=>{
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){
      const choices=[...root.current.querySelectorAll('.canvas-model-menu input,.canvas-model-menu button:not(:disabled)')];
      const index=choices.indexOf(document.activeElement);
      if(choices.length){e.preventDefault();choices[(index+(e.key==='ArrowDown'?1:-1)+choices.length)%choices.length].focus();}
    }
  }}>
    <CanvasComposerPopover className="canvas-model-picker" menuClassName="canvas-model-menu" label="Choose model" menuLabel="Available models" title={selected?`${selected.name} · ${selected.provider||selected.id} · ${selected.tier}`:'Choose model'} disabled={disabled} trigger={<><span>{selected?.name||'Choose model'}</span><small>{selected?.tier||''}</small><span aria-hidden="true">⌄</span></>}>
      <input type="search" aria-label="Search models" placeholder="Search models…" value={search} onChange={e=>setSearch(e.target.value)} />
      <div className="canvas-model-options">{rows.map(m=><button type="button" key={m.id} disabled={disabled||!eligible(m)} aria-pressed={m.id===catalogue.selected} onClick={async()=>{await onSelect(m.id);root.current.querySelector('[popover]').hidePopover();root.current.querySelector('.canvas-composer-trigger').focus();}}>
        <span>{m.name}<small>{m.provider?`${m.provider} · `:''}{m.id}</small></span><span>{m.id===catalogue.selected?'✓ ':''}{m.tier==='paid'&&!catalogue.allow_paid_models?'Paid · enable in Settings':m.tier==='unknown'?'Unverified':m.tier}</span>
      </button>)}{!rows.length&&<p>No matching models.</p>}</div>
      <button type="button" disabled={disabled} onClick={onRefresh}>Refresh models</button>
    </CanvasComposerPopover>
  </div>;
}
