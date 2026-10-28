import React from 'react';
import { EditDialog, Field, Text } from './ModeUI';
import { allPages } from './workspaceData';
import { jsonBody } from './api';

export default function ChatSave({api,kind,message,projects,projectId,conversationId,onSaved,onClose,registerGuard}) {
 const available=projects.filter(p=>!p.archived);
 return <EditDialog title={kind==='tasks'?'Create task from response':'Create note from response'} registerGuard={registerGuard} initial={{project_id:projectId||available[0]?.id||'',title:message.content.split('\n').find(s=>s.trim())?.replace(/^#+\s*/, '').slice(0,200)||'Chat response',content:message.content.slice(0,kind==='tasks'?19500:49500)}} onClose={onClose} onSave={async d=>{
   if(!d.project_id)throw Error('Choose a project first.');
   const source=`\n\nSource conversation: #/chat?conversation=${conversationId}`;
   let row;
   if(kind==='tasks'){
     const columns=await allPages(api,`/projects/${d.project_id}/columns`);
     const column=columns.find(c=>!c.is_done);
     if(!column)throw Error('Create a non-completion stage in this project first.');
     row=(await api(`/projects/${d.project_id}/tasks`,{method:'POST',...jsonBody({title:d.title,description:d.content+source,column_id:column.id})})).task;
   }else row=await api(`/projects/${d.project_id}/notes`,{method:'POST',...jsonBody({title:d.title,content:d.content+source})});
   onSaved({kind,row,projectId:Number(d.project_id)});
 }}>{(d,c)=><><p>Review this AI response before saving. Your confirmation creates one project record; no additional AI call is made.</p><Field label="Destination project"><select required value={d.project_id} onChange={e=>c('project_id',Number(e.target.value))}><option value="">Choose project</option>{available.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></Field><Text label="Title" required maxLength={200} value={d.title} onChange={v=>c('title',v)}/><Text label={kind==='tasks'?'Task description':'Note content'} multiline rows={10} maxLength={kind==='tasks'?19500:49500} value={d.content} onChange={v=>c('content',v)}/>{message.content.length>(kind==='tasks'?19500:49500)&&<p role="status">This response is longer than the destination limit. Only the displayed excerpt will be saved.</p>}</>}</EditDialog>;
}
