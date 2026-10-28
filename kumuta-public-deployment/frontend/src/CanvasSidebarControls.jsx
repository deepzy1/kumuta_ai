import React, {useEffect, useRef, useState} from 'react';
import {boundedWidth, sidebarPreference, saveSidebarPreference, SIDEBAR_DEFAULT, SIDEBAR_MIN, SIDEBAR_MAX} from './canvasSidebar.js';
import './canvasSidebar.css';

const storage = () => {try{return window.localStorage;}catch{return null;}};

export function useCanvasSidebar(accountId) {
  const [value, setValue] = useState(() => sidebarPreference(storage(), accountId));
  useEffect(() => { setValue(sidebarPreference(storage(), accountId)); }, [accountId]);
  const update = patch => setValue(old => {
    const next = {...old, ...patch};
    saveSidebarPreference(storage(), accountId, next);
    return next;
  });
  return {...value, update};
}

export function SidebarResize({sidebar}) {
  const drag = useRef(null);
  const finish = event => { if (!drag.current) return; drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); };
  return <div className="canvas-sidebar-resize" role="separator" tabIndex={0} aria-label="Resize Canvas AI sidebar" aria-orientation="vertical" aria-valuemin={SIDEBAR_MIN} aria-valuemax={SIDEBAR_MAX} aria-valuenow={sidebar.width}
    onPointerDown={event => { if(event.button !== 0)return; event.preventDefault();event.stopPropagation();drag.current={x:event.clientX,width:sidebar.width};event.currentTarget.setPointerCapture(event.pointerId); }}
    onPointerMove={event => { if(!drag.current)return;event.stopPropagation();sidebar.update({width:boundedWidth(drag.current.width + drag.current.x - event.clientX)}); }}
    onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={()=>{drag.current=null;}}
    onKeyDown={event => {const widths={ArrowLeft:sidebar.width+20,ArrowRight:sidebar.width-20,Home:SIDEBAR_MIN,End:SIDEBAR_MAX};if(event.key in widths){event.preventDefault();event.stopPropagation();sidebar.update({width:boundedWidth(widths[event.key])});}}} />;
}

export function SidebarButtons({sidebar}) {
  return <><button aria-label={sidebar.pinned?'Unpin Canvas AI sidebar':'Pin Canvas AI sidebar'} title={sidebar.pinned?'Unpin sidebar':'Pin sidebar'} aria-pressed={sidebar.pinned} onClick={()=>sidebar.update({pinned:!sidebar.pinned})}>⌖</button><button aria-label="Reset sidebar width" title="Reset sidebar width" onClick={()=>sidebar.update({width:SIDEBAR_DEFAULT})}>↔</button></>;
}
