import {MAX_FILE, MAX_FILES, MAX_TOTAL} from './attachments.js';

export const CANVAS_ACCEPT='.pdf,.docx,.txt,.md,.markdown,.csv,.xlsx,.png,.jpg,.jpeg';
export const CANVAS_TYPES='PDF, DOCX, TXT, Markdown, CSV, XLSX, PNG or JPG';
const types={pdf:['application/pdf'],docx:['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
  txt:['text/plain'],md:['text/markdown','text/x-markdown','text/plain'],markdown:['text/markdown','text/x-markdown','text/plain'],csv:['text/csv','application/csv','text/plain','application/vnd.ms-excel'],
  xlsx:['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],png:['image/png'],jpg:['image/jpeg'],jpeg:['image/jpeg'],webp:['image/webp']};
export function attachmentKind(file){const ext=file.name.split('.').pop().toLowerCase();return ['png','jpg','jpeg','webp'].includes(ext)?'image':['csv','xlsx'].includes(ext)?'dataset':'document';}
export function validateCanvasFiles(existing,incoming){
  const all=[...existing,...incoming];
  if(all.length>MAX_FILES)return 'Attach up to 5 files per message.';
  for(const f of incoming){
    const ext=f.name.split('.').pop().toLowerCase(),allowed=types[ext];
    if(ext==='webp')return 'WebP decoding is unavailable under the current dependency policy. Use PNG or JPEG.';
    if(!allowed||f.type&&!allowed.includes(f.type)&&f.type!=='application/octet-stream')return `Choose ${CANVAS_TYPES}.`;
    const limit=attachmentKind(f)==='dataset'?4*1024*1024:MAX_FILE;
    if(!f.size||f.size>limit)return `${f.name}: choose a nonempty ${attachmentKind(f)==='dataset'?'spreadsheet up to 4 MiB':'file up to 8 MiB'}.`;
  }
  if(all.reduce((n,f)=>n+f.size,0)>MAX_TOTAL)return 'Attachments exceed the 20 MiB draft limit.';
  return '';
}

// Removing a chip removes its request scope, while the authorized library keeps
// the source. Never unlink/delete a shared original as a draft side effect.
export function withoutAttachmentSource(value,resource,resources=[]){
  if(!resource)return value;
  const keys=value.scope==='board'?resources.filter(r=>r.status==='ready'&&['document','dataset'].includes(r.kind)).map(r=>`${r.kind}:${r.source_id}`):value.keys;
  return {...value,scope:value.scope==='board'?'selected':value.scope,keys:keys.filter(k=>k!==`${resource.kind}:${resource.source_id}`),confirmFull:false,...(value.analyses?{analyses:[]}: {})};
}

// A processing failure is recoverable draft state, not a permanent Send lock.
export function canvasAttachmentState(entries){
  const current=entries.filter(f=>f.status!=='removed');
  return {ready:current.filter(f=>f.status==='ready'),failed:current.filter(f=>['error','failed'].includes(f.status)),
    waiting:current.some(f=>['selected','uploading','retrying','queued','processing'].includes(f.status))};
}
