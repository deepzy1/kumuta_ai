import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

export default function Modal({ title, children, onClose, busy = false, wide = false, drawer = false }) {
  const titleId = useId();
  const panel = useRef(null);
  const close = useRef(onClose);
  const pending = useRef(busy);
  close.current = onClose;
  pending.current = busy;
  useEffect(() => {
    const previous = document.activeElement;
    const root = document.getElementById('root');
    const wasInert = root?.inert;
    if (root) root.inert = true;
    const focusable = () => [...panel.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')]
      .filter(node => node.getClientRects().length);
    (focusable()[0] || panel.current).focus();
    function keydown(event) {
      if (!panel.current.contains(document.activeElement)) return;
      if (event.key === 'Escape') { event.preventDefault(); if (!pending.current) close.current(); }
      if (event.key === 'Tab') {
        const nodes = focusable();
        if (!nodes.length) { event.preventDefault(); panel.current.focus(); return; }
        const first = nodes[0], last = nodes.at(-1);
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', keydown);
    return () => {
      document.removeEventListener('keydown', keydown);
      if (root) root.inert = wasInert;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return createPortal(<div className={`ws-modal-backdrop ${drawer ? 'drawer-backdrop' : ''}`} onClick={event => {
    if (event.target === event.currentTarget && !busy) onClose();
  }}><section ref={panel} tabIndex={-1} className={`ws-modal ${wide ? 'wide' : ''} ${drawer ? 'drawer' : ''}`}
      role="dialog" aria-modal="true" aria-labelledby={titleId} aria-busy={busy}>
    <header><h2 id={titleId}>{title}</h2><button type="button" className="icon" aria-label={`Close ${title}`} disabled={busy} onClick={onClose}>✕</button></header>
    {children}
  </section></div>, document.body);
}

export function ErrorNotice({ error, retry }) {
  return error ? <div className="ws-error" role="alert"><span>{error}</span>{retry && <button className="secondary" onClick={retry}>Try again</button>}</div> : null;
}

export function Empty({ title, children }) {
  return <div className="ws-empty"><h3>{title}</h3><p>{children}</p></div>;
}
