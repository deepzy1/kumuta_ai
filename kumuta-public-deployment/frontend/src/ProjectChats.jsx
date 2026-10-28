import { jsonBody } from './api';
import React, { useEffect, useState } from 'react';
import { allPages } from './workspaceData';
import { Empty, ErrorNotice } from './Modal';

export default function ProjectChats({ api, project, documents, onNewChat, onChat, onMoveChat, onLibraryChanged }) {
  const [chats, setChats] = useState([]), [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [search, setSearch] = useState(''), [reload, setReload] = useState(0);
  const [importing,setImporting]=useState(false),[notice,setNotice]=useState('');
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    setLoading(true); setError('');
    (async () => {
      const conversations = await allPages(api, `/conversations?project_id=${project.id}`, options);
      if (controller.signal.aborted) return;
      setChats(conversations);
      if (documents) {
        const attachments = [];
        for (const chat of conversations) {
          let before = '';
          for (;;) {
            const page = await api(`/conversations/${chat.id}?limit=100${before}`, options);
            for (const message of page.messages) {
              const list = message.attachments?.length ? message.attachments : message.attachment_name ? [message] : [];
              for (const file of list) attachments.push({ ...file, aid: message.attachments?.length ? file.id : null, mid: message.id, chat });
            }
            if (!page.has_more) break;
            if (!page.messages.length) throw new Error('Conversation changed while loading its files. Try again.');
            before = `&before=${page.messages[0].id}`;
          }
        }
        if (!controller.signal.aborted) setFiles(attachments);
      }
    })().catch(e => { if (e.name !== 'AbortError') setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, project.id, documents, reload]);
  async function download(file) {
    try {
      const blob = await api(`/conversations/${file.chat.id}/attachments/${file.mid}${file.aid ? `/${file.aid}` : ''}`, { responseType: 'blob' });
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url; link.download = file.attachment_name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e.message); }
  }
  const query = search.toLowerCase();
  const shownChats = chats.filter(chat => chat.title.toLowerCase().includes(query));
  const shownFiles = files.filter(file => `${file.attachment_name} ${file.chat.title}`.toLowerCase().includes(query));
  return <div className="ws-chat-list"><div className="ws-section-heading"><div><h2>{documents ? 'Chat attachments' : 'Project conversations'}</h2><p className="muted">{documents ? 'Files already attached to this project’s conversations.' : 'Talk ideas through with your project context close at hand.'}</p></div><button className="primary compact" disabled={project.archived} onClick={onNewChat}>{documents ? 'Attach in a new chat' : '+ New conversation'}</button></div>
    {documents && <p className="ws-info">Original chat attachments stay here. Use Documents above for searchable files and cited retrieval, or open a chat to attach images and PDFs directly.</p>}
    <input type="search" aria-label={documents ? 'Search project attachments' : 'Search project conversations'} placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} />
    <p role="status">{notice}</p><ErrorNotice error={error} retry={() => setReload(n => n + 1)} />
    {loading ? <p role="status" className="ws-loading">Loading {documents ? 'attachments' : 'conversations'}…</p> : documents ? <>
      {shownFiles.map(file => <div className="ws-chat-row" key={`${file.chat.id}-${file.mid}-${file.aid || 'legacy'}`}><div><strong>{file.attachment_name}</strong><small>{file.attachment_mime} · {file.attachment_size ? `${Math.ceil(file.attachment_size / 1024)} KB` : 'Legacy attachment'}</small><button className="ws-text-button" onClick={() => onChat(file.chat.id)}>{file.chat.title}</button></div><div className="mode-actions"><button className="secondary" onClick={() => download(file)}>Download</button>{file.attachment_mime==='application/pdf'&&<button className="secondary" disabled={project.archived||importing} onClick={async()=>{if(importing)return;setImporting(true);try{const row=await api(`/conversations/${file.chat.id}/attachments/${file.mid}/library`,{method:'POST',...jsonBody({attachment_id:file.aid})});setError('');onLibraryChanged?.();setNotice(row.duplicate?'This PDF is already in Project Documents.':'PDF saved to Project Documents. Open the library above to study from it.');}catch(e){setError(e.message);}finally{setImporting(false);}}}>Save PDF to Documents</button>}</div></div>)}
      {!shownFiles.length && <Empty title={search ? 'No matching attachments' : 'No attachments yet'}>Files from project chats will appear here.</Empty>}
    </> : <>
      {shownChats.map(chat => <div className="ws-chat-row" key={chat.id}><button className="ws-chat-open" onClick={() => onChat(chat.id)}><strong>{chat.title}</strong><small>{chat.updated_at ? new Date(chat.updated_at).toLocaleDateString() : 'Saved conversation'} · Open conversation →</small></button><button className="secondary" onClick={() => onMoveChat(chat)}>Move</button></div>)}
      {!shownChats.length && <Empty title={search ? 'No matching conversations' : 'Start a conversation'}>Create a project chat, or use Move from an existing conversation to bring it here.</Empty>}
    </>}
  </div>;
}
