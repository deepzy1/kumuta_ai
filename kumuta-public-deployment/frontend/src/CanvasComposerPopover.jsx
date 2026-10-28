import React, { useEffect, useId, useRef, useState } from 'react';

// Native popovers escape the sidebar's clipping and retain form/React context.
export default function CanvasComposerPopover({className='',menuClassName='',label,menuLabel,title,trigger,disabled,children,triggerRef}) {
  const id=useId(),button=useRef(null),menu=useRef(null);
  const [open,setOpen]=useState(false);
  function position(){
    const panel=menu.current,rect=button.current.getBoundingClientRect();
    const width=Math.min(360,window.innerWidth-24);
    panel.style.width=`${width}px`;
    panel.style.left=`${Math.max(12,Math.min(rect.left,window.innerWidth-width-12))}px`;
    panel.style.bottom=`${window.innerHeight-rect.top+8}px`;
    panel.style.maxHeight=`${Math.max(0,rect.top-20)}px`;
  }
  useEffect(()=>{
    const panel=menu.current;
    const toggle=()=>{
      const visible=panel.matches(':popover-open');setOpen(visible);
      if(visible){position();panel.querySelector('input,select,button:not(:disabled)')?.focus();}
    };
    const reposition=()=>{if(panel.matches(':popover-open'))position();};
    // Visible-source shortcuts can open this popover while focus remains on
    // their external button. Capture Escape before the board dismiss handler.
    const keyboard=e=>{if(e.key==='Escape'&&panel.matches(':popover-open')){e.preventDefault();e.stopPropagation();panel.hidePopover();button.current.focus();}};
    panel.addEventListener('toggle',toggle);
    document.addEventListener('keydown',keyboard,true);
    window.addEventListener('resize',reposition);
    window.addEventListener('scroll',reposition,true);
    const observer=new ResizeObserver(reposition);observer.observe(button.current);
    return()=>{panel.removeEventListener('toggle',toggle);document.removeEventListener('keydown',keyboard,true);window.removeEventListener('resize',reposition);window.removeEventListener('scroll',reposition,true);observer.disconnect();};
  },[]);
  useEffect(()=>{if(disabled)menu.current.hidePopover();},[disabled]);
  return <div className={`canvas-composer-picker ${className}`} onKeyDown={e=>{
    if(e.key==='Escape'&&(menu.current.matches(':popover-open')||menu.current.contains(e.target))){e.preventDefault();e.stopPropagation();menu.current.hidePopover();button.current.focus();}
  }}>
    <button type="button" ref={node=>{button.current=node;if(triggerRef)triggerRef.current=node;}} className="canvas-composer-trigger" aria-label={label} title={title||label} aria-expanded={open} aria-controls={id} disabled={disabled} onClick={()=>{position();menu.current.togglePopover();}}>{trigger}</button>
    <div id={id} ref={menu} popover="auto" className={`canvas-composer-popover ${menuClassName}`} role="group" aria-label={menuLabel||`${label} options`} onKeyDown={e=>{
      if(e.key==='Tab'){
        const controls=[...menu.current.querySelectorAll('input:not(:disabled),select:not(:disabled),button:not(:disabled),summary')].filter(node=>node.getClientRects().length);
        if((e.shiftKey&&document.activeElement===controls[0])||(!e.shiftKey&&document.activeElement===controls.at(-1))){e.preventDefault();menu.current.hidePopover();button.current.focus();}
      }
    }}>{children}</div>
  </div>;
}
