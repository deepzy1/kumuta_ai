import React, { useMemo } from 'react';
import DOMPurify from 'dompurify';

// D7-0 requires a separately hosted executable origin. No script permission,
// network, forms, popups, navigation links, host bridge or credentials here.
export function previewDocument(payload) {
  const html = DOMPurify.sanitize(payload.html, {
    ALLOWED_TAGS: ['div','span','p','h1','h2','h3','h4','strong','em','small','br','hr','ul','ol','li','table','thead','tbody','tr','td','th','pre','code','label','input','button','section','article'],
    ALLOWED_ATTR: ['class','style','type','value','min','max','step','disabled','aria-label'],
    ALLOW_DATA_ATTR: false,
  });
  const css = payload.css.replace(/</g, '\\3c ');
  return `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; media-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"><meta name="referrer" content="no-referrer"><style>${css}</style></head><body>${html}</body></html>`;
}
export default function CustomPreview({ payload }) {
  const document = useMemo(() => previewDocument(payload), [payload]);
  return <div className="custom-preview"><p>HTML/CSS preview · JavaScript disabled</p><iframe title="Isolated custom UI preview" sandbox="" referrerPolicy="no-referrer" allow="camera 'none'; microphone 'none'; geolocation 'none'; clipboard-read 'none'; clipboard-write 'none'" srcDoc={document} /></div>;
}
