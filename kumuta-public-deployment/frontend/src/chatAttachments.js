import {attachmentKind, validateCanvasFiles} from './canvasAttachments.js';
import {jsonBody} from './api.js';
export {attachmentKind};
export const CHAT_ACCEPT='.pdf,.docx,.txt,.md,.markdown,.csv,.xlsx,.png,.jpg,.jpeg';
export const validateChatFiles = validateCanvasFiles;

const pause = signal => new Promise((resolve,reject)=>{
  const cancelled=()=>{clearTimeout(timer);reject(new DOMException('Upload cancelled','AbortError'));};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',cancelled);resolve();},500);
  if(signal.aborted)cancelled();else signal.addEventListener('abort',cancelled,{once:true});
});
export async function prepareChatFile(entry, cid, api, signal, update) {
  const kind=attachmentKind(entry.file);
  if(kind==='image')return entry;
  const base=kind==='dataset'?`/conversations/${cid}/datasets`:'/documents';
  let source=entry.source;
  if(source?.status==='error'){
    source=await api(`${base}/${source.id}/retry`,{method:'POST',signal,...jsonBody({revision:source.revision})});
  } else if(!source) {
    const body=new FormData();body.append('file',entry.file);
    if(kind==='document')body.append('conversation_id',String(cid));
    update({status:'uploading',progress:0});
    source=await api(base,{method:'POST',body,signal,onUploadProgress:progress=>update({progress})});
  }
  update({source,status:source.status,progress:100});
  const deadline=Date.now()+120000;
  while(['queued','processing'].includes(source.status)){
    if(Date.now()>deadline)throw Error('Processing is taking longer than expected. Retry checks the existing upload.');
    await pause(signal);
    source=await api(`${base}/${source.id}`,{signal});
    update({source,status:source.status});
  }
  if(source.status!=='ready')throw Error(source.error||'File processing failed. Retry or remove it.');
  return {...entry,source,status:'ready',progress:100};
}
