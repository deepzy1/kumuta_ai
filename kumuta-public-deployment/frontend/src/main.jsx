import { browserSignIn, canvasURL, watchSession } from './platformSession.js';
import {authHeaders} from './api.js';
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDown,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  FileText,
  Image,
  KeyRound,
  LoaderCircle,
  LogOut,
  Menu,
  MessageSquare,
  PanelLeftClose,
  Paperclip,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Trash2,
  Workflow,
  ListTodo,
  StickyNote,
  X,
} from "lucide-react";
import { API, jsonBody, readEvents, request } from "./api";
import Markdown, { CopyButton } from "./Markdown";
import Settings from "./Settings";
import { RememberDialog } from './Memory';
import Modal from './Modal';
import './context.css';
import DocumentsPanel, { DocumentPreview, DocumentSources } from './Documents';
import { documentPrompt } from './documents';
import AttachmentPreview from "./AttachmentPreview";
import { clipboardImages } from "./attachments";
import {CHAT_ACCEPT,validateChatFiles,attachmentKind,prepareChatFile} from "./chatAttachments.js";
import ChatDatasets from "./ChatDatasets.jsx";
import QuickUIMessage from "./QuickUI";
import { QuickUIContext, useQuickUISettings } from "./QuickUISettings";
import "./style.css";
import "./workspace.css";
import useWorkspaces from "./useWorkspaces";
import WorkspaceNav, { projectTabs, tabLabel } from "./WorkspaceNav";
import ContextSwitcher from "./ContextSwitcher";
import { readRoute, routeHash } from "./navigation";
import ChatSave from './ChatSave';
import ProjectScreen, { ProjectsHome } from "./ProjectScreen";
import { WorkspaceDialog, MoveChatDialog } from "./WorkspaceDialogs";
import "./theme.css";

const formatSize = (bytes) =>
  bytes < 1024 * 1024
    ? `${Math.ceil(bytes / 1024)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;


function Brand({ large = false }) {
  return (
    <div className={`brand ${large ? "large" : ""}`}>
      <span className="brand-symbol">
        <MessageSquare />
        <Sparkles />
      </span>
      {!large && <span>Kumuta AI</span>}
    </div>
  );
}
function conversationGroup(conversation) {
  if (!conversation.updated_at) return "Older";
  const date = new Date(conversation.updated_at);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const week = new Date(today);
  week.setDate(week.getDate() - 7);
  return date >= today
    ? "Today"
    : date >= yesterday
      ? "Yesterday"
      : date >= week
        ? "Previous 7 Days"
        : "Older";
}
function relativeDate(value) {
  if (!value) return "Saved conversation";
  const date = new Date(value),
    minutes = Math.floor((Date.now() - date) / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} hours ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Auth({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await request("", `/auth/${mode}`, {
        method: "POST",
        ...jsonBody({ email, password }),
      });
      setPassword("");
      await onAuth(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <div className="auth-top">
        <Brand />
        <span>Your ideas. More possibilities.</span>
      </div>
      <div className="auth-content">
        <div className="auth-story">
          <span className="eyebrow">
            <Sparkles size={15} /> A LITTLE CURIOSITY GOES A LONG WAY
          </span>
          <h1>
            A clearer path
            <br />
            from <em>what if</em>
            <br />
            to what’s next.
          </h1>
          <p>
            A thoughtful space to ask, create, and understand.
            <br />
            Powered by Gemini. Made yours with Kumuta AI.
          </p>
          <div className="story-features">
            <span>
              <MessageSquare size={17} /> Private conversations
            </span>
            <span>
              <Paperclip size={17} /> Images & documents
            </span>
            <span>
              <KeyRound size={17} /> Your own API key
            </span>
          </div>
          <div className="auth-decoration">
            <Sparkles size={70} />
          </div>
        </div>
        <form className="auth-card" onSubmit={submit}>
          <Brand large />
          <h2>
            {mode === "login" ? "Welcome back" : "A fresh start for your ideas"}
          </h2>
          <p>
            {mode === "login"
              ? "Log in to your Kumuta AI workspace."
              : "Create your account, then connect your Gemini key."}
          </p>
          <label htmlFor="auth-email">Email address</label>
          <input
            id="auth-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            autoComplete={
              mode === "login" ? "current-password" : "new-password"
            }
            minLength={8}
            maxLength={128}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
          />
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button className="primary" disabled={busy}>
            {busy && <LoaderCircle className="spin" size={17} />}{" "}
            {mode === "login" ? "Log in" : "Create account"}
            <ArrowUpRight size={18} />
          </button>
          <p className="auth-switch">
            {mode === "login"
              ? "New to Kumuta AI?"
              : "Already have an account?"}{" "}
            <button
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "signup" : "login");
                setError("");
              }}
            >
              {mode === "login" ? "Create an account" : "Log in"}
            </button>
          </p>
          <div className="auth-privacy">
            <ShieldCheck size={15} /> A private workspace, connected to your own
            key.
          </div>
        </form>
      </div>
      <footer className="auth-footer">
        © 2026 Kumuta AI <span>Designed & Developed by Deepak R</span>
      </footer>
    </div>
  );
}

function App() {
  const [view, setView] = useState(() => readRoute(window.location.hash));
  const [tutorRequest, setTutorRequest] = useState(null);
  const [workspaceDialog, setWorkspaceDialog] = useState(null);
  const [movingChat, setMovingChat] = useState(null);
  const [chatProject, setChatProject] = useState(null);
  const leaveGuard = useRef(() => true);
  const registerGuard = useCallback(guard => {
    leaveGuard.current = guard;
    return () => { if (leaveGuard.current === guard) leaveGuard.current = () => true; };
  }, []);
  const [token, setToken] = useState(
    () => "",
  );
  const [account, setAccount] = useState(null);
  const [sessionReady,setSessionReady]=useState(false);
  const [conversations, setConversations] = useState([]);
  const [historyMore, setHistoryMore] = useState(false);
  const [search, setSearch] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [cid, setCid] = useState(null);
  const [currentTitle, setCurrentTitle] = useState("New conversation");
  const [messages, setMessages] = useState([]);
  const [messagesMore, setMessagesMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState(null);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState([]);
  const filesRef = useRef([]);
  const attachmentId = useRef(0);
  const attachmentUploads = useRef(new Map()), uploadConversation = useRef(null);
  const [datasetRequests,setDatasetRequests] = useState([]);
  const [sourceRefresh,setSourceRefresh] = useState(0);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const [busy, setBusy] = useState(false);
  const [compacting, setCompacting] = useState(false);
  const [error, setError] = useState("");
  const [sidebar, setSidebar] = useState(() => window.innerWidth > 900);
  useEffect(() => {
    const panel = document.querySelector('.sidebar');
    const content = document.querySelector('.app-content');
    const sync = () => { if (content) content.inert = sidebar && window.innerWidth <= 900; };
    sync();
    const keyboard = event => {
      if (!sidebar || window.innerWidth > 900 || !panel) return;
      if (event.key === 'Escape') { event.preventDefault(); setSidebar(false); requestAnimationFrame(() => document.querySelector('[aria-label="Open sidebar"]')?.focus()); }
      if (event.key === 'Tab') {
        const nodes = [...panel.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href]')].filter(n => n.getClientRects().length);
        const first = nodes[0], last = nodes.at(-1);
        if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
      }
    };
    if (sidebar && window.innerWidth <= 900) panel?.querySelector('button')?.focus();
    window.addEventListener('resize', sync); document.addEventListener('keydown', keyboard);
    return () => { if (content) content.inert = false; window.removeEventListener('resize', sync); document.removeEventListener('keydown', keyboard); };
  }, [sidebar, token]);
  const [popover, setPopover] = useState(null);
  const profile = popover === "profile";
  const modelOpen = popover === "model";
  const contextOpen = popover === "context";
  const [freeOnly, setFreeOnly] = useState(false);
  const [models, setModels] = useState([]);
  const [modelLoading, setModelLoading] = useState(false);
  const [context, setContext] = useState(null);
  const [settings, setSettings] = useState(null);
  const [rememberContent, setRememberContent] = useState(null);
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [chatSave,setChatSave]=useState(null),[savedItem,setSavedItem]=useState(null);
  const [importingPdf,setImportingPdf]=useState(false),[importedPdf,setImportedPdf]=useState(null);
  const [documentBusy, setDocumentBusy] = useState(false);
  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [documentMode, setDocumentMode] = useState('search');
  const [documentSource, setDocumentSource] = useState(null);
  const [webSearch, setWebSearch] = useState(false);
  const [quickuiBehavior, setQuickuiBehavior] = useState("");
  const [chatAppearance, setChatAppearance] = useState(null);
  const [following, setFollowing] = useState(true);
  const controller = useRef(null);
  const submitting = useRef(false);
  const scroller = useRef(null);
  const follow = useRef(true);
  const fileInput = useRef(null);
  const textarea = useRef(null);
  const viewRequest = useRef(0);
  const searchRequest = useRef(0);
  const currentId = useRef(null);
  const active = busy || compacting || loading;

  const logout = useCallback((revoke=true) => {
    if (revoke !== false) request('', '/auth/logout', {method:'POST'}).catch(()=>{});
    controller.current?.abort();
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("email");
    sessionStorage.removeItem("kumuta-focus-project");
    sessionStorage.removeItem("kumuta-workspace");
    window.history.replaceState(null, "", "#/chat");
    viewRequest.current++;
    currentId.current = null;
    setToken("");
    setAccount(null);
    setCid(null);
    setMessages([]);
    setConversations([]);
    setModels([]);
    setSettings(null);
    setRememberContent(null);
    setDatasetRequests([]); setTutorRequest(null); setDocumentsOpen(false); setSelectedDocuments([]); setDocumentMode('search'); setDocumentSource(null);
    setError("");
    setPopover(null);
    setWebSearch(false);
    setQuickuiBehavior("");
    setChatAppearance(null);
    setView({ screen: 'chat' });
    setWorkspaceDialog(null);
    setMovingChat(null);
    setChatProject(null);
    leaveGuard.current = () => true;
    clearFiles();
    setInput("");
  }, []);
  const api = useCallback(
    async (path, options) => {
      try {
        return await request(token, path, options);
      } catch (e) {
        if (e.status === 401) logout(false);
        throw e;
      }
    },
    [token, logout],
  );
  const closeSettings = useCallback(() => setSettings(null), []);
  const identity = useRef(null);
  useEffect(() => {
    if (!token) { identity.current=null; return; }
    return watchSession(path=>request(token,path), data=>{
      if(identity.current && identity.current!==data.id){sessionStorage.removeItem('token');window.location.reload();return;}
      identity.current=data.id;
    },()=>logout(false));
  },[token,logout]);
  useEffect(()=>{
    let alive=true;
    (async()=>{try{
      let account=await request('','/auth/session');
      if(!account.authenticated){
        const legacy=sessionStorage.getItem('token');
        if(!legacy||legacy==='cookie')return;
        account=await request(legacy,'/auth/me');
        await browserSignIn({token:legacy});
      }
      if(alive){sessionStorage.setItem('token','cookie');setAccount(account);setToken('cookie');}
    }catch(e){if(alive)setError(e.message);}finally{if(alive)setSessionReady(true);}})();
    return()=>{alive=false;};
  },[]);
  const quickuiSettings = useQuickUISettings(api, token);
  const workspaceStore = useWorkspaces(api, token);

  function navigate(next, force = false, restoring = false) {
    if (!force && (active || !leaveGuard.current())) return false;
    if (view.screen === 'chat' && next.screen !== 'chat') clearFiles();
    if (next.screen === 'projects' && !next.workspaceId) next = { ...next, workspaceId: workspaceStore.workspaceId };
    setPopover(null);
    setView(next);
    const hash = routeHash(next);
    if (!restoring && window.location.hash !== hash) window.history.pushState(null, "", hash);
    if (window.innerWidth <= 900) setSidebar(false);
    return true;
  }
  function workspaceAction(type) {
    if (active || !leaveGuard.current()) return;
    setPopover(null); setSettings(null); setWorkspaceDialog(type);
  }

  async function loadModels(refresh = false) {
    setModelLoading(true);
    try {
      const result = await api(`/models${refresh ? "?refresh=true" : ""}`);
      setModels(result.models);
      setAccount((previous) =>
        previous ? { ...previous, preferred_model: result.selected } : previous,
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setModelLoading(false);
    }
  }
  const loadHistory = useCallback(
    async (query = "", offset = 0) => {
      const sequence = ++searchRequest.current;
      setHistoryLoading(true);
      try {
        const result = await api(
          `/conversations?q=${encodeURIComponent(query)}&offset=${offset}`,
        );
        if (sequence !== searchRequest.current) return;
        setConversations((previous) =>
          offset ? [...previous, ...result.items] : result.items,
        );
        setHistoryMore(result.has_more);
      } catch (e) {
        if (sequence === searchRequest.current) setError(e.message);
      } finally {
        if (sequence === searchRequest.current) setHistoryLoading(false);
      }
    },
    [api],
  );
  useEffect(() => {
    if (!token) return;
    let alive = true;
    api("/auth/me")
      .then((data) => {
        if (alive) {
          setAccount(data);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [token, api]);
  useEffect(() => {
    if (!token) return;
    const timer = setTimeout(() => loadHistory(search), 180);
    return () => {
      clearTimeout(timer);
      searchRequest.current++;
    };
  }, [token, search, loadHistory]);
  useEffect(() => {
    if (account?.has_api_key) loadModels();
    else {
      setModels([]);
      setContext(null);
    }
  }, [account?.has_api_key, token]);
  useEffect(() => {
    const outside = (event) => {
      if (!event.target.closest?.(`[data-popover="${popover}"]`))
        setPopover(null);
    };
    const escape = (event) => {
      if (event.key === "Escape") {
        setPopover(null);
        document.querySelector(`[data-popover="${popover}"] > button`)?.focus();
      }
    };
    if (!popover) return;
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", escape);
    };
  }, [popover]);
  useEffect(() => {
    if (settings) setPopover(null);
  }, [settings]);
  useEffect(() => {
    const preventFileNavigation = (event) => {
      if (Array.from(event.dataTransfer?.types || []).includes("Files"))
        event.preventDefault();
      if (event.type === "drop" || event.type === "dragend") {
        dragDepth.current = 0;
        setDragging(false);
      }
    };
    window.addEventListener("dragover", preventFileNavigation);
    window.addEventListener("drop", preventFileNavigation);
    window.addEventListener("dragend", preventFileNavigation);
    return () => {
      window.removeEventListener("dragover", preventFileNavigation);
      window.removeEventListener("drop", preventFileNavigation);
      window.removeEventListener("dragend", preventFileNavigation);
    };
  }, []);
  useEffect(() => {
    if (follow.current && scroller.current)
      scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages, busy]);
  useEffect(() => {
    const pane = scroller.current;
    const content = pane?.querySelector(".message-content");
    if (!content) return;
    const observer = new ResizeObserver(() => {
      if (follow.current) pane.scrollTop = pane.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [token]);
  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 160)}px`;
    }
  }, [input]);
  // Browsing saved chats is local. Provider token counting is an explicit action.
  useEffect(() => setContext(null), [cid, account?.preferred_model]);
  useEffect(() => () => controller.current?.abort(), []);

  async function signedIn(credentials) {
    const result = await browserSignIn(credentials);
    sessionStorage.setItem("token", result.token);
    setToken(result.token);
    setAccount(result);
    setError("");
  }
  async function selectConversation(id, restoring = false) {
    if (submitting.current || compacting || !navigate({ screen: 'chat', conversationId: id }, false, restoring)) return;
    clearFiles(); setDatasetRequests([]);
    const sequence = ++viewRequest.current;
    currentId.current = id;
    setCid(id);
    setChatProject(null);
    setTutorRequest(null); setSelectedDocuments([]); setDocumentMode('search'); setDocumentsOpen(false);
    setCurrentTitle('Loading conversation…');
    setQuickuiBehavior("");
    setMessages([]);
    setSummary(null);
    setError("");
    setLoading(true);
    setPopover(null);
    follow.current = true;
    setFollowing(true);
    if (window.innerWidth <= 900) setSidebar(false);
    try {
      const data = await api(`/conversations/${id}`);
      if (sequence !== viewRequest.current) return;
      const project = data.project_id ? await api(`/projects/${data.project_id}`) : null;
      if (sequence !== viewRequest.current) return;
      setChatProject(project);
      if (project && project.workspace_id !== workspaceStore.workspaceId) workspaceStore.setWorkspaceId(project.workspace_id);
      setTutorRequest(data.messages.findLast(m => m.role === 'user')?.document_request?.tutor || null);
      setMessages(data.messages);
      setDatasetRequests(data.messages.findLast(m=>m.role==='user')?.document_request?.datasets||[]);
      setMessagesMore(data.has_more);
      setSummary(data.summary);
      setChatAppearance(data.quickui_appearance);
      setCurrentTitle(data.title);
    } catch (e) {
      if (sequence === viewRequest.current) setError(e.message);
    } finally {
      if (sequence === viewRequest.current) setLoading(false);
    }
  }
  function newChat(project = null, documentIds = [], tutor = null, restoring = false) {
    if (active || submitting.current || !navigate({ screen: 'chat', ...(project ? { projectId: project.id } : {}) }, false, restoring)) return;
    setChatProject(project);
    setTutorRequest(tutor);
    setDatasetRequests([]); setSelectedDocuments(documentIds); setDocumentMode('search'); setDocumentsOpen(false);
    setPopover(null);
    viewRequest.current++;
    currentId.current = null;
    setCid(null);
    setCurrentTitle("New conversation");
    setMessages([]);
    setMessagesMore(false);
    setSummary(null);
    setChatAppearance(null);
    setQuickuiBehavior("");
    setWebSearch(false);
    setInput("");
    clearFiles();
    setError("");
    setContext(null);
    if (window.innerWidth <= 900) setSidebar(false);
    textarea.current?.focus();
  }
  const restoredToken = useRef(null);
  useEffect(() => {
    if (!token) { restoredToken.current = null; return; }
    async function restore() {
      if (active || !leaveGuard.current()) {
        window.history.pushState(null, '', routeHash({ ...view, ...(cid ? { conversationId: cid } : {}) }));
        return;
      }
      const next = readRoute(window.location.hash);
      if (next.screen !== 'chat') {
        if (next.screen === 'projects' && next.workspaceId) workspaceStore.setWorkspaceId(next.workspaceId);
        if (next.projectId) {
          try { const project = await api(`/projects/${next.projectId}`); workspaceStore.setWorkspaceId(project.workspace_id); }
          catch (e) { setError(e.message); return; }
        }
        navigate(next, true, true);
      } else if (next.conversationId) await selectConversation(next.conversationId, true);
      else if (next.projectId) {
        try { const project = await api(`/projects/${next.projectId}`); workspaceStore.setWorkspaceId(project.workspace_id); newChat(project, [], null, true); }
        catch (e) { setError(e.message); }
      } else newChat(null, [], null, true);
    }
    window.addEventListener('popstate', restore);
    if (restoredToken.current !== token) { restoredToken.current = token; restore(); }
    return () => window.removeEventListener('popstate', restore);
  }, [token, api, active, view, cid]);
  useEffect(() => {
    if (token && view.screen === 'chat' && cid && !loading) {
      const hash = routeHash({ screen: 'chat', conversationId: cid });
      if (window.location.hash !== hash) window.history.replaceState(null, '', hash);
    }
  }, [token, view.screen, cid, loading]);
  function openModule(tab) {
    if (chatProject) navigate({ screen: 'project', projectId: chatProject.id, tab });
    else { setModulePicker(tab); }
  }
  const [modulePicker, setModulePicker] = useState(null);
  async function loadEarlier() {
    if (active || !messages.length) return;
    setLoading(true);
    const id = cid;
    const pane = scroller.current,
      oldHeight = pane.scrollHeight;
    try {
      const data = await api(`/conversations/${id}?before=${messages[0].id}`);
      if (currentId.current !== id) return;
      follow.current = false;
      setFollowing(false);
      setMessages((previous) => [...data.messages, ...previous]);
      setMessagesMore(data.has_more);
      requestAnimationFrame(() => {
        pane.scrollTop += pane.scrollHeight - oldHeight;
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  async function rename(conversation) {
    const title = window
      .prompt("Rename conversation", conversation.title)
      ?.trim();
    if (!title) return;
    try {
      await api(`/conversations/${conversation.id}`, {
        method: "PATCH",
        ...jsonBody({ title }),
      });
      if (cid === conversation.id) setCurrentTitle(title);
      await loadHistory(search);
    } catch (e) {
      setError(e.message);
    }
  }
  async function remove(conversation) {
    if (!window.confirm("Delete this conversation and its attachments?"))
      return;
    try {
      await api(`/conversations/${conversation.id}`, { method: "DELETE" });
      if (cid === conversation.id) newChat();
      await loadHistory(search);
    } catch (e) {
      setError(e.message);
    }
  }
  async function chooseModel(model) {
    if (active) return;
    setPopover(null);
    try {
      setAccount(
        await api("/settings/model", {
          method: "PATCH",
          ...jsonBody({ model }),
        }),
      );
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  function togglePopover(name) {
    setPopover((previous) => (previous === name ? null : name));
  }
  function clearFiles() {
    attachmentUploads.current.forEach(controller=>controller.abort());attachmentUploads.current.clear();uploadConversation.current=null;
    filesRef.current = [];
    setFiles([]);
  }
  function addFiles(chosen) {
    if (active) return;
    const incoming = Array.from(chosen || []);
    if (!incoming.length) return;
    const problem = validateChatFiles(
      filesRef.current.map((item) => item.file),
      incoming,
    );
    if (problem) {
      setError(problem);
      return;
    }
    const updated = [
      ...filesRef.current,
      ...incoming.map((file) => ({ id: ++attachmentId.current, file, status:attachmentKind(file)==='image'?'ready':'selected' })),
    ];
    filesRef.current = updated;
    setFiles(updated);
    setError("");
    updated.filter(item=>item.status==='selected').forEach(startAttachmentUpload);
  }
  function removeFile(id) {
    attachmentUploads.current.get(id)?.abort();attachmentUploads.current.delete(id);
    const entry=filesRef.current.find(item=>item.id===id);
    if(entry?.source&&attachmentKind(entry.file)==='dataset')setDatasetRequests(old=>old.filter(v=>v.dataset_id!==entry.source.id));
    const updated = filesRef.current.filter((item) => item.id !== id);
    filesRef.current = updated;
    setFiles(updated);
  }
  function updateAttachment(id,patch) {
    if(!filesRef.current.some(item=>item.id===id))return;
    filesRef.current=filesRef.current.map(item=>item.id===id?{...item,...patch}:item);setFiles(filesRef.current);
  }
  async function startAttachmentUpload(entry) {
    if(attachmentUploads.current.has(entry.id))return;
    const abort=new AbortController();attachmentUploads.current.set(entry.id,abort);
    updateAttachment(entry.id,{status:'uploading',error:''});
    try {
      let destination=currentId.current;
      if(!destination){
        if(!uploadConversation.current)uploadConversation.current=api('/conversations',{method:'POST',signal:abort.signal,...jsonBody({project_id:chatProject?.id??null})});
        const created=await uploadConversation.current;
        if(abort.signal.aborted||!filesRef.current.some(item=>item.id===entry.id))return;
        destination=created.id;
        if(currentId.current!==destination){currentId.current=destination;setCid(destination);setCurrentTitle(created.title);setConversations(old=>[created,...old.filter(c=>c.id!==destination)]);}
      }
      if(abort.signal.aborted)return;
      const ready=await prepareChatFile(entry,destination,api,abort.signal,patch=>updateAttachment(entry.id,patch));
      if(abort.signal.aborted||currentId.current!==destination)return;
      updateAttachment(entry.id,ready);
      if(attachmentKind(entry.file)==='dataset'){
        setSourceRefresh(v=>v+1);
        setDatasetRequests(old=>old.some(v=>v.dataset_id===ready.source.id)?old:[...old,{dataset_id:ready.source.id,sha256:ready.source.sha256,sheet:ready.source.sheets[0]?.name||null}]);
      }
    }catch(e){if(e.name!=='AbortError')updateAttachment(entry.id,{status:'error',error:e.message});}
    finally{attachmentUploads.current.delete(entry.id);if(!currentId.current)uploadConversation.current=null;}
  }
  function pasteImages(event) {
    if (active || settings || event.target !== textarea.current) return;
    const images = clipboardImages(event.clipboardData);
    if (!images.length) return;
    // Leave the browser's normal text paste intact for mixed text/image clips.
    if (!event.clipboardData.getData("text/plain")) event.preventDefault();
    addFiles(images);
  }
  function dragEnter(event) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }
  function dragLeave(event) {
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (!dragDepth.current) setDragging(false);
  }
  function dropFiles(event) {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }
  async function togglePaidModels(enabled) {
    setPopover(null);
    try {
      setAccount(
        await api("/settings/model-access", {
          method: "PATCH",
          ...jsonBody({ allow_paid_models: enabled }),
        }),
      );
    } catch (e) {
      setError(e.message);
    }
  }
  function attachAny() {
    fileInput.current.accept =
      CHAT_ACCEPT;
    fileInput.current.click();
  }
  async function downloadAttachment(message, attachment) {
    try {
      const result = await fetch(
        `${API}/conversations/${cid}/attachments/${message.id}${attachment.id ? `/${attachment.id}` : ""}`,
        {credentials:"include", headers:authHeaders(token)},
      );
      if (!result.ok) throw new Error("Could not load this attachment.");
      const url = URL.createObjectURL(await result.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = attachment.attachment_name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e.message);
    }
  }
  async function generate(regenerate = false) {
    if (
      submitting.current ||
      active ||
      (!regenerate && !input.trim() && !files.length) ||
      (!regenerate && files.some(item=>item.status!=='ready'))
    )
      return;
    if (!account?.has_api_key) {
      setSettings("key");
      return;
    }
    const summaryMode = regenerate ? messages.findLast(m => m.role === 'user')?.document_request?.mode : documentMode;
    if (summaryMode && summaryMode !== 'search' && !window.confirm('Process complete selected documents? Long documents can use up to 20 summary requests plus the final answer, charged to your selected Gemini model. Continue?')) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setPopover(null);
    follow.current = true;
    setFollowing(true);
    const abort = new AbortController();
    controller.current = abort;
    let id = cid,
      started = false;
    const pending = `stream-${Date.now()}`;
    let streamError = "";
    try {
      if (!id) {
        const created = await api("/conversations", {
          method: "POST",
          signal: abort.signal,
          ...jsonBody({ project_id: chatProject?.id ?? null }),
        });
        id = created.id;
        currentId.current = id;
        setCid(id);
        setCurrentTitle(created.title);
        setConversations((previous) => [created, ...previous]);
      }
      const body = new FormData();
      body.append("text", input.trim());
      if (tutorRequest) body.append("tutor_request", JSON.stringify(tutorRequest));
      body.append("web_search", String(webSearch));
      body.append('document_ids', JSON.stringify([...new Set([...selectedDocuments,...files.filter(item=>attachmentKind(item.file)==='document'&&item.source?.status==='ready').map(item=>item.source.id)])]));
      body.append('dataset_requests',JSON.stringify(datasetRequests));
      body.append('document_mode', documentMode);
      body.append('confirm_document_summary', String(documentMode !== 'search'));
      if (quickuiBehavior) body.append("quickui_behavior", quickuiBehavior);
      files.filter(item=>attachmentKind(item.file)==='image').forEach(({ file }) => body.append("attachments", file));
      const response = await fetch(
        `${API}/conversations/${id}/${regenerate ? `regenerate?web_search=${webSearch}${quickuiBehavior ? `&quickui_behavior=${quickuiBehavior}` : ""}` : "messages"}`,
        {
          method: "POST",
          credentials:"include", headers:authHeaders(token),
          ...(regenerate ? {} : { body }),
          signal: abort.signal,
        },
      );
      if (response.status === 401) {
        logout();
        return;
      }
      await readEvents(response, (event, data) => {
        if (event === "start") {
          started = true;
          setContext(data.context);
          setCurrentTitle(data.title);
          setConversations((previous) =>
            previous.map((c) =>
              c.id === id
                ? {
                    ...c,
                    title: data.title,
                    updated_at: new Date().toISOString(),
                  }
                : c,
            ),
          );
          if (!regenerate) {
            setInput("");
            clearFiles();
          }
          setMessages((previous) => {
            const history =
              regenerate && previous.at(-1)?.role === "assistant"
                ? previous.slice(0, -1)
                : previous;
            return [
              ...history,
              ...(data.message ? [data.message] : []),
              {
                id: pending,
                role: "assistant",
                content: "",
                model: data.model,
                status: "generating",
              },
            ];
          });
        } else if (event === "context") {
          setContext(data);
        } else if (event === "delta") {
          setMessages((previous) =>
            previous.map((m) =>
              m.id === pending ? { ...m, content: m.content + data.text } : m,
            ),
          );
        } else if (event === "error") {
          streamError = data.message;
          setError(data.message);
        } else if (event === "done") {
          setMessages((previous) =>
            previous.flatMap((m) =>
              m.id === pending ? (data.message ? [data.message] : []) : [m],
            ),
          );
        }
      });
    } catch (e) {
      if (e.name !== "AbortError")
        setError(
          e.message === "Failed to fetch"
            ? "Connection interrupted. Check your connection and try again."
            : e.message,
        );
    } finally {
      controller.current = null;
      if (id && currentId.current === id && started) {
        try {
          // Give the disconnect handler a moment to save a stopped response.
          if (abort.signal.aborted)
            await new Promise((resolve) => setTimeout(resolve, 300));
          const data = await api(`/conversations/${id}`);
          if (currentId.current === id) {
            setMessages((previous) => [
              ...previous.filter(
                (m) =>
                  typeof m.id === "number" &&
                  m.id < (data.messages[0]?.id || 0),
              ),
              ...data.messages,
            ]);
            if (messages.length <= data.messages.length)
              setMessagesMore(data.has_more);
            setSummary(data.summary);
          }
        } catch (e) {
          if (!streamError) setError(e.message);
        }
      }
      if (currentId.current === id) await loadHistory(search);
      submitting.current = false;
      setBusy(false);
      textarea.current?.focus();
    }
  }
  async function compact() {
    if (active || !cid) return;
    setCompacting(true);
    setError("");
    setPopover(null);
    try {
      const result = await api(`/conversations/${cid}/summarize`, {
        method: "POST",
      });
      setSummary(result.summary);
    } catch (e) {
      setError(e.message);
    } finally {
      setCompacting(false);
    }
  }
  function openSettings(tab) {
    setPopover(null);
    setSettings(tab);
    if (window.innerWidth <= 900) setSidebar(false);
  }
  function scrollDown() {
    follow.current = true;
    setFollowing(true);
    scroller.current?.scrollTo({
      top: scroller.current.scrollHeight,
      behavior: "smooth",
    });
  }
  const selectedModel =
    models.find((model) => model.id === account?.preferred_model) ||
    (!account?.preferred_model
      ? models.find((model) => model.tier === "free")
      : null);
  const title = currentTitle;
  const groups = ["Today", "Yesterday", "Previous 7 Days", "Older"];
  if (!sessionReady) return <main className="auth-page" role="status">Checking your Kumuta session…</main>;
  if (!token) return <Auth onAuth={signedIn} />;
  return (
    <QuickUIContext.Provider value={quickuiSettings}>
    <div className={`layout ${sidebar ? "sidebar-visible" : ""} ${!messages.length && view.screen === 'chat' ? "chat-home" : ""}`}>
      <aside
        className={`sidebar ${sidebar ? "open" : ""}`}
        aria-label="Workspace and chat sidebar"
        aria-hidden={!sidebar} inert={sidebar ? undefined : ''}
      >
        <div className="side-top">
          <Brand />
          <button
            className="icon"
            aria-label="Collapse sidebar"
            onClick={() => {
              setPopover(null);
              setSidebar(false);
            }}
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
        <button className="new" onClick={() => newChat(view.screen === 'project' ? workspaceStore.projects.find(p => p.id === view.projectId) : chatProject)} disabled={active}>
          <Plus size={18} /> New Chat
        </button>
        <WorkspaceNav view={view} disabled={active} onNavigate={navigate} onNewChat={() => newChat()} />
        <a className="ws-nav" href={canvasURL(workspaceStore.workspaceId,view.screen === 'project' ? view.projectId : null)} target="_blank" rel="noopener noreferrer">▧ Canvas ↗</a>
        <div className="search-box">
          <Search size={15} />
          <input
            aria-label="Search conversations"
            placeholder="Search conversations…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              className="icon"
              aria-label="Clear search"
              onClick={() => setSearch("")}
            >
              <X size={13} />
            </button>
          )}
        </div>
        <div className="history">
          {groups.map((group) => {
            const items = conversations.filter(
              (conversation) => conversationGroup(conversation) === group,
            );
            return (
              items.length > 0 && (
                <section className="history-group" key={group}>
                  <h3>
                    {group}
                    <ChevronDown size={12} />
                  </h3>
                  {items.map((conversation) => (
                    <div
                      className={`history-item ${cid === conversation.id ? "active" : ""}`}
                      key={conversation.id}
                    >
                      <button
                        className="chat-select"
                        disabled={active}
                        onClick={() => selectConversation(conversation.id)}
                      >
                        <MessageSquare size={16} />
                        <span>
                          <strong>{conversation.title}</strong>
                          <small>
                            {conversation.project_id ? workspaceStore.projects.find(p => p.id === conversation.project_id)?.name || 'Project chat' : 'General Chat'} · {relativeDate(conversation.updated_at)}
                          </small>
                        </span>
                      </button>
                      <div className="history-actions">
                        <button
                          className="icon small"
                          disabled={active}
                          aria-label={`Rename ${conversation.title}`}
                          onClick={() => rename(conversation)}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          className="icon small"
                          disabled={active}
                          aria-label={`Delete ${conversation.title}`}
                          onClick={() => remove(conversation)}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </section>
              )
            );
          })}
          {!conversations.length && (
            <div className="history-empty">
              {historyLoading
                ? "Loading conversations…"
                : search
                  ? "No conversations found."
                  : "Your next idea starts with a new chat."}
            </div>
          )}
          {historyMore && (
            <button
              className="load-more"
              disabled={historyLoading}
              onClick={() => loadHistory(search, conversations.length)}
            >
              {historyLoading ? "Loading…" : "Load more chats"}
            </button>
          )}
        </div>
        <button className="sidebar-settings ws-nav" onClick={() => openSettings('account')}><Settings2 size={18} />Settings</button>
        <div className="profile-area" data-popover="profile">
          {profile && (
            <div className="profile-menu">
              <div className="profile-heading">
                <strong>{account?.email?.split("@")[0]}</strong>
                <small>{account?.email}</small>
              </div>
              <button onClick={() => openSettings("key")}>
                <KeyRound size={17} />
                My API Key
                <span
                  className={`status-dot ${account?.has_api_key ? "green" : ""}`}
                />
              </button>
              <button onClick={() => openSettings("account")}>
                <Settings2 size={17} />
                Account Settings
              </button>
              <button onClick={() => openSettings("usage")}>
                <BarChart3 size={17} />
                Usage & Limits
              </button>
              <a
                onClick={() => setPopover(null)}
                href="https://ai.google.dev/gemini-api/docs"
                target="_blank"
                rel="noreferrer"
              >
                <BookOpen size={17} />
                Gemini documentation
                <ArrowUpRight size={14} />
              </a>
              <button className="logout" onClick={logout}>
                <LogOut size={17} />
                Sign out
              </button>
            </div>
          )}
          <button
            className="account"
            aria-label="Open profile menu"
            aria-expanded={profile}
            onClick={() => togglePopover("profile")}
          >
            <span className="avatar">
              {(account?.email || "K")[0].toUpperCase()}
            </span>
            <span className="account-details">
              <strong>
                {account?.email?.split("@")[0] || "Your account"}
              </strong>
              <small>{account?.email || "Loading…"}</small>
            </span>
            <ChevronDown size={15} />
          </button>
        </div>
      </aside>
      {sidebar && (
        <button
          className="sidebar-overlay"
          aria-label="Close sidebar"
          onClick={() => {
            setPopover(null);
            setSidebar(false);
          }}
        />
      )}
      <div className="app-content">
      <header className="app-topbar">
        {!sidebar && <button className="icon" aria-label="Open sidebar" onClick={() => setSidebar(true)}><Menu size={20} /></button>}
        <ContextSwitcher store={workspaceStore} projectId={view.screen === 'project' ? view.projectId : chatProject?.id} disabled={active}
            onWorkspace={id => { if (navigate({ screen: 'projects', workspaceId: id })) workspaceStore.setWorkspaceId(id); }}
            onProject={project => { workspaceStore.setWorkspaceId(project.workspace_id); newChat(project); }} onGeneral={() => newChat()} onAction={workspaceAction} />
        <span className="topbar-workspace">{workspaceStore.workspace?.name}</span>
        <button className="icon" aria-label="Open account settings" onClick={() => openSettings('account')}><span className="avatar">{(account?.email || 'K')[0].toUpperCase()}</span></button>
      </header>
      <main className="ws-main" hidden={view.screen === 'chat'}>
        <div className="ws-main-scroll">
          {view.screen === 'projects' && <ProjectsHome api={api} store={workspaceStore} onCreate={() => workspaceAction('project-create')} onProject={id => navigate({ screen: 'project', projectId: id, tab: 'overview' })} />}
          {view.screen === 'project' && <ProjectScreen initialItemId={view.itemId} key={`${view.projectId}-${view.refresh || 0}`} api={api} projectId={view.projectId} tab={view.tab || 'overview'}
            onTab={tab => tab === 'chats' ? newChat(workspaceStore.projects.find(p => p.id === view.projectId)) : navigate({ ...view, tab, itemId:undefined })} settingsSection={view.settingsSection} onAccountSettings={openSettings} onNewChat={newChat} onChat={selectConversation} onMoveChat={setMovingChat}
            onChanged={workspaceStore.refreshProjects} registerGuard={registerGuard}
            onFocusScreen={() => setSidebar(false)}
            onAssist={(project, prompt) => { newChat(project); setInput(prompt); }}
            onTutor={(project, controls, prompt) => { newChat(project, [], controls); setInput(prompt); }}
            onAskDocuments={(project, ids, mode) => { newChat(project, ids); setDocumentMode(mode); setInput(documentPrompt(mode)); }}
            onDeleted={() => { setChatProject(p => p?.id === view.projectId ? null : p); navigate({ screen: 'projects' }, true); workspaceStore.refreshProjects(); loadHistory(search); }} />}
        </div>
      </main>
      <main
        hidden={view.screen !== 'chat'}
        onPaste={pasteImages}
        onDragEnter={dragEnter}
        onDragLeave={dragLeave}
        onDragOver={(event) => {
          if (Array.from(event.dataTransfer.types).includes("Files")) {
            event.preventDefault();
            event.dataTransfer.dropEffect = active ? "none" : "copy";
            setDragging(true);
          }
        }}
        onDrop={dropFiles}
      >
        {chatProject && <nav className="ws-tabs" aria-label="Project sections">{projectTabs.map(tab => <button key={tab} className={tab === 'chats' ? 'active' : ''} aria-current={tab === 'chats' ? 'page' : undefined} disabled={active} onClick={() => tab === 'chats' ? undefined : openModule(tab)}>{tabLabel(tab)}</button>)}</nav>}
        <div className="chat-context-actions"><button className="secondary" disabled={active} onClick={() => openSettings("memory")}>AI &amp; Memory</button>
          <button className="secondary" disabled={active} onClick={async () => {
            if (submitting.current || loading) return;
            setLoading(true);
            try {
              if (!cid) { const created = await api('/conversations', { method: 'POST', ...jsonBody({ project_id: chatProject?.id ?? null }) }); currentId.current = created.id; setCid(created.id); setConversations(previous => [created, ...previous]); }
              setDocumentsOpen(true);
            } catch (e) { setError(e.message); } finally { setLoading(false); }
          }}>Documents{selectedDocuments.length ? ` · ${selectedDocuments.length} selected` : ''}</button>
          {tutorRequest && <span className="mode-origin">AI tutor · <select aria-label="Tutor level" value={tutorRequest.level} disabled={active} onChange={e => setTutorRequest({ ...tutorRequest, level: e.target.value })}>{['beginner','intermediate','advanced'].map(x => <option key={x}>{x}</option>)}</select><select aria-label="Tutor explanation depth" value={tutorRequest.depth} disabled={active} onChange={e => setTutorRequest({ ...tutorRequest, depth: e.target.value })}>{['brief','balanced','detailed'].map(x => <option key={x}>{x}</option>)}</select><button className="secondary" disabled={active} onClick={() => setTutorRequest(null)}>Exit tutor</button></span>}
          {!!selectedDocuments.length && <><select aria-label="Chat document mode" value={documentMode} disabled={active} onChange={e => setDocumentMode(e.target.value)}><option value="search">Passage search</option><option value="summarize">Complete summary</option><option value="compare">Complete comparison</option></select><button className="secondary" disabled={active} onClick={() => { setSelectedDocuments([]); setDocumentMode('search'); }}>Clear documents</button></>}
        </div>
        {cid && <button className="ws-chat-move" disabled={active} onClick={() => { setPopover(null); setMovingChat({ id: cid, project_id: chatProject?.id ?? null }); }}>Move conversation</button>}
        {dragging && (
          <div className="drop-overlay" role="status">
            <div>
              <Paperclip size={36} />
              <strong>
                {active
                  ? "Wait for the current operation to finish"
                  : "Drop images or PDFs here"}
              </strong>
              <span>Up to 5 files · 8 MB each · 20 MB total</span>
            </div>
          </div>
        )}
        <header className="chat-header">
          <div className="header-title">

            <MessageSquare size={18} className="title-icon" />
            <strong title={title}>{title}</strong>
          </div>
          <div className="header-controls">
            {cid && !context && account?.has_api_key && <button className="secondary" disabled={active} aria-label="Check conversation context" onClick={async () => {
              const id = cid;
              try { const result = await api(`/conversations/${id}/context`); if (currentId.current === id) setContext(result); }
              catch (e) { setError(e.message); }
            }}>Check context</button>}
            {context && (
              <div className="context-wrap" data-popover="context">
                <button
                  className={`context-pill ${context.near_limit ? "warning" : ""}`}
                  aria-expanded={contextOpen}
                  aria-label="Conversation context usage"
                  onClick={() => {
                    togglePopover("context");
                  }}
                >
                  <span
                    className="context-ring"
                    style={{
                      "--progress": `${Math.min(context.percentage || 0, 100)}%`,
                    }}
                  />
                  <span>
                    {context.estimated ? "~" : ""}
                    {context.percentage === null
                      ? "Context"
                      : `${Math.round(context.percentage)}%`}
                    <span className="context-label"> context</span>
                  </span>
                </button>
                {contextOpen && (
                  <div className="context-popover popover">
                    <h3>Conversation context</h3>
                    <strong>
                      {context.estimated ? "Estimated " : ""}
                      {context.used_tokens.toLocaleString()}{" "}
                      <span>
                        / {context.max_tokens?.toLocaleString() || "unknown"}{" "}
                        tokens
                      </span>
                    </strong>
                    <p>
                      This is the current history sent to {context.model},
                      including attachments and any saved summary. It is
                      separate from your cumulative usage.
                    </p>
                    <button
                      className="secondary"
                      disabled={active || !messages.length}
                      onClick={() => {
                        setPopover(null);
                        compact();
                      }}
                    >
                      {compacting ? "Compacting…" : "Compact context"}
                    </button>
                    <small>Original messages and files are preserved.</small>
                  </div>
                )}
              </div>
            )}
            <div className="model-wrap" data-popover="model">
              <button
                className="model-button"
                disabled={active}
                aria-expanded={modelOpen}
                onClick={() => {
                  if (!account?.has_api_key) {
                    openSettings("key");
                    return;
                  }
                  togglePopover("model");
                }}
              >
                <Sparkles size={15} />
                <span>
                  {selectedModel?.name ||
                    (account?.has_api_key
                      ? "Select model"
                      : "Connect Gemini")}
                </span>
                <ChevronDown size={13} />
              </button>
              {modelOpen && (
                <div className="model-menu popover">
                  <div className="model-menu-title">
                    <strong>Select Model</strong>
                    <button
                      className="icon"
                      title="Refresh models"
                      aria-label="Refresh models"
                      disabled={modelLoading}
                      onClick={() => loadModels(true)}
                    >
                      <RefreshCw
                        size={14}
                        className={modelLoading ? "spin" : ""}
                      />
                    </button>
                  </div>
                  <div className="model-filters">
                    <button
                      className="secondary"
                      aria-pressed={freeOnly}
                      onClick={() => setFreeOnly((value) => !value)}
                    >
                      {freeOnly ? "Show all models" : "Free only"}
                    </button>
                    <button
                      className="secondary"
                      onClick={() => {
                        setFreeOnly(false);
                        setModels((previous) =>
                          [...previous].sort(
                            (a, b) =>
                              Number(b.tier === "free") -
                                Number(a.tier === "free") ||
                              a.name.localeCompare(b.name),
                          ),
                        );
                        document
                          .querySelector(".model-menu")
                          ?.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    >
                      Sort by Free
                    </button>
                  </div>
                  <p className="model-note">
                    Free-tier compatible. Your Google project’s billing and
                    quota still apply.
                  </p>
                  {modelLoading && !models.length && (
                    <p className="muted">Loading models…</p>
                  )}
                  {[
                    ["free", "Free Tier"],
                    ["paid", "Paid API / Billing Required"],
                    ["unknown", "Eligibility unverified"],
                  ].map(([tier, label]) => {
                    const group = models.filter(
                      (model) => model.tier === tier,
                    );
                    if (!group.length || (freeOnly && tier !== "free"))
                      return null;
                    return (
                      <section
                        key={tier}
                        className="model-section"
                        aria-label={label}
                      >
                        <h4>{label}</h4>
                        {tier === "paid" && (
                          <label className="paid-opt-in">
                            <input
                              type="checkbox"
                              checked={!!account?.allow_paid_models}
                              onChange={(event) =>
                                togglePaidModels(event.target.checked)
                              }
                            />{" "}
                            Enable paid models (Google billing required)
                          </label>
                        )}
                        {tier === "unknown" && (
                          <p className="model-note">
                            No current pricing match. Refresh to check again;
                            these models are disabled.
                          </p>
                        )}
                        {group.map((model) => (
                          <button
                            className={`model-option ${selectedModel?.id === model.id ? "selected" : ""}`}
                            key={model.id}
                            disabled={
                              tier === "unknown" ||
                              (tier === "paid" && !account?.allow_paid_models)
                            }
                            title={
                              tier === "paid"
                                ? "Requires a billing-enabled Google project and opt-in"
                                : tier === "unknown"
                                  ? "Free-tier eligibility has not been verified"
                                  : model.id
                            }
                            onClick={() => chooseModel(model.id)}
                          >
                            <MessageSquare size={17} />
                            <span>
                              <strong>
                                {model.name}{" "}
                                <em className={`model-badge ${tier}`}>
                                  {tier === "free"
                                    ? "Free"
                                    : tier === "paid"
                                      ? "Paid"
                                      : "Unverified"}
                                </em>
                              </strong>
                              <small>{model.id}</small>
                              {model.description && (
                                <small>{model.description}</small>
                              )}
                              {model.input_token_limit && (
                                <small>
                                  {model.input_token_limit.toLocaleString()}{" "}
                                  token context
                                </small>
                              )}
                            </span>
                            {selectedModel?.id === model.id && (
                              <Check size={17} />
                            )}
                          </button>
                        ))}
                      </section>
                    );
                  })}
                  {!models.some((model) => model.tier === "free") && (
                    <p className="model-note">
                      No verified free models found. Refresh the list or check
                      your key in AI Studio.
                    </p>
                  )}
                  <a
                    className="pricing-source"
                    href="https://ai.google.dev/gemini-api/docs/pricing"
                    target="_blank"
                    rel="noreferrer"
                    onClick={() => setPopover(null)}
                  >
                    Google pricing ·{" "}
                    {models[0]?.pricing_checked_at
                      ? `checked ${new Date(models[0].pricing_checked_at).toLocaleDateString()}`
                      : "verification unavailable"}
                  </a>
                </div>
              )}
            </div>

          </div>
        </header>
        <section
          ref={scroller}
          className="messages"
          aria-label="Conversation messages"
          aria-busy={busy}
          onScroll={() => {
            const pane = scroller.current;
            follow.current =
              pane.scrollHeight - pane.scrollTop - pane.clientHeight < 100;
            setFollowing(follow.current);
          }}
        >
          <div
            className={`message-content ${messages.length === 0 ? "empty-content" : ""}`}
          >
            {messagesMore && (
              <button
                className="load-more older"
                disabled={active}
                onClick={loadEarlier}
              >
                Load earlier messages
              </button>
            )}
            {loading && (
              <div className="loading-chat">
                <LoaderCircle className="spin" size={18} /> Loading
                conversation…
              </div>
            )}
            {!messages.length && !loading && (
              <div className="welcome">
                <h1>{new Date().getHours() < 12 ? 'Good morning' : new Date().getHours() < 18 ? 'Good afternoon' : 'Good evening'}, {account?.email?.split('@')[0] || 'there'}</h1>
                <p>What would you like to work on today?</p>
                <div className="quick-actions">
                  {[[MessageSquare, 'Chat with AI', 'Get answers, write, brainstorm', 'chat', 'violet'], [BarChart3, 'Analyze data', 'Explore your CSV or Excel files', 'data', 'green'], [BookOpen, 'Study & Learn', 'Create courses and practice', 'study', 'violet'], [ListTodo, 'Plan & Manage Tasks', 'Organize your next step', 'tasks', 'orange'], [StickyNote, 'Create Notes', 'Capture ideas as they happen', 'notes', 'orange'], [Workflow, 'Generate Reports', 'Turn saved data into insights', 'reports', 'violet']].map(([Icon, label, detail, target, color]) => <button key={target} disabled={active} onClick={() => target === 'chat' ? textarea.current?.focus() : openModule(target)}><span className={`quick-icon ${color}`}><Icon size={23} /></span><span><strong>{label}</strong><small>{detail}</small></span></button>)}
                </div>
                {!account?.has_api_key && (
                  <button
                    className="connect-note"
                    onClick={() => openSettings("key")}
                  >
                    <KeyRound size={15} />
                    Connect your Gemini key to get started
                    <ArrowUpRight size={14} />
                  </button>
                )}
              </div>
            )}
            {importedPdf&&<div className="ws-info" role="status">PDF {importedPdf.doc.duplicate?'already available':'saved'} in Project Documents. <button className="ws-text-button" onClick={()=>{navigate({screen:'project',projectId:importedPdf.projectId,tab:'documents'});setImportedPdf(null);}}>Open Project Documents →</button></div>}{savedItem&&<div className="ws-info" role="status">Saved {savedItem.kind==='tasks'?'task':'note'}: {savedItem.row.title}. <button className="ws-text-button" onClick={()=>{navigate({screen:'project',projectId:savedItem.projectId,tab:savedItem.kind,itemId:savedItem.row.id});setSavedItem(null);}}>Open created {savedItem.kind==='tasks'?'task':'note'} →</button></div>}{summary && (
              <details className="summary-box">
                <summary>
                  <ShieldCheck size={14} /> Context compacted · original
                  history preserved
                </summary>
                <Markdown text={summary} />
              </details>
            )}
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={message.id}>
                {message.role === "assistant" && (
                  <div className="assistant-heading">
                    <Brand large />
                    <strong>Kumuta AI</strong>
                    {message.model ? (
                      <span className="response-model">{message.model}</span>
                    ) : (
                      <span className="response-model">
                        Legacy response · model unrecorded
                      </span>
                    )}
                    {message.created_at && (
                      <time>
                        {new Date(message.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </time>
                    )}
                  </div>
                )}
                <div className="bubble">
                  {(message.attachments?.length
                    ? message.attachments
                    : message.attachment_name
                      ? [
                          {
                            attachment_name: message.attachment_name,
                            attachment_mime: message.attachment_mime,
                            attachment_size: message.attachment_size,
                          },
                        ]
                      : []
                  ).map((attachment) => (
                    <button
                      key={attachment.id || "legacy"}
                      className="attachment-card"
                      title="Download attachment"
                      onClick={() => downloadAttachment(message, attachment)}
                    >
                      <span
                        className={`attachment-icon ${attachment.attachment_mime === "application/pdf" ? "pdf" : ""}`}
                      >
                        {attachment.attachment_mime === "application/pdf" ? (
                          <FileText size={24} />
                        ) : (
                          <Image size={24} />
                        )}
                      </span>
                      <span>
                        <strong>{attachment.attachment_name}</strong>
                        <small>
                          {attachment.attachment_size
                            ? formatSize(attachment.attachment_size)
                            : "Attachment"}{" "}
                          · Download
                        </small>
                      </span>
                      <ArrowUpRight size={14} />
                    </button>
                  ))}
                  {message.role === "assistant" ? (
                    <>
                      {message.content ? (
                        <QuickUIMessage
                          message={message}
                          onTableAction={context=>{setInput(`${context.action==='ask'?'Ask about':context.action} these ${context.scope} rows from response ${message.id}. Use only these supplied rows and their stated filters. Do not infer complete-dataset totals.\n${JSON.stringify({columns:context.block.columns,rows:context.rows,row_ids:context.row_ids,scope:context.scope,query:context.query,filters:context.filters})}`);document.querySelector('textarea[aria-label="Message Kumuta AI"]')?.focus();}}
                          api={api}
                          cid={cid}
                          chatAppearance={chatAppearance}
                          onChatAppearance={setChatAppearance}
                          behavior={quickuiBehavior || quickuiSettings.preferences.behavior}
                        />
                      ) : (
                        <div className="thinking">
                          <span className="thinking-dots">
                            <i />
                            <i />
                            <i />
                          </span>{" "}
                          Thinking it through…
                        </div>
                      )}
                      {message.status === "generating" && message.content && (
                        <span className="generation-cursor" />
                      )}
                      {message.status === "stopped" && (
                        <p className="response-note">Generation stopped</p>
                      )}
                      {message.status === "error" && (
                        <p className="response-note">Response interrupted</p>
                      )}
                    </>
                  ) : (
                    <><div className="user-text">{message.content}</div>{message.document_request?.sources?.map(source=><div className="attachment-card" key={`${source.kind}-${source.id}-${source.sheet||''}`}><FileText size={18}/><span><strong>{source.filename}</strong><small>{source.sheet||'Document source'}</small></span></div>)}</>
                  )}
                </div>
                {(message.attachments?.length?message.attachments:message.attachment_name?[message]:[]).filter(a=>a.attachment_mime==='application/pdf').map(a=><div className="message-memory" key={`library-${a.id||message.id}`}><button disabled={active||importingPdf} onClick={async()=>{if(!chatProject){setMovingChat(conversations.find(c=>c.id===cid));return;}if(importingPdf)return;setImportingPdf(true);try{const doc=await api(`/conversations/${cid}/attachments/${message.id}/library`,{method:'POST',...jsonBody({attachment_id:message.attachments?.length?a.id:null})});setImportedPdf({doc,projectId:doc.project_id});}catch(e){setError(e.message);}finally{setImportingPdf(false);}}}>{chatProject?'Save PDF to Project Documents':'Move chat to a project to save PDF'}</button></div>)}
                {message.role === 'assistant' && <DocumentSources sources={message.document_sources} onOpen={setDocumentSource} />}
                {message.content && message.status !== 'generating' && <div className="message-memory"><button disabled={active} onClick={() => setRememberContent(message.content)}>Remember this</button></div>}
                {message.role === "assistant" &&
                  message.status !== "generating" && (
                    <div className="response-actions">
                      <button disabled={active||!message.content} onClick={()=>setChatSave({kind:'tasks',message})}>Create task</button><button disabled={active||!message.content} onClick={()=>setChatSave({kind:'notes',message})}>Save as note</button><CopyButton
                        text={message.content}
                        label="Copy response"
                      />
                      {index === messages.length - 1 && (
                        <button
                          disabled={active}
                          onClick={() => generate(true)}
                        >
                          <RefreshCw size={14} />
                          Regenerate
                        </button>
                      )}
                    </div>
                  )}
              </article>
            ))}
            {busy && messages.at(-1)?.status !== "generating" && (
              <div className="thinking">
                <LoaderCircle className="spin" size={16} /> Preparing your
                request…
              </div>
            )}
            {compacting && (
              <div className="thinking">
                <LoaderCircle className="spin" size={16} /> Compacting context
                while preserving your history…
              </div>
            )}
            {!busy && messages.at(-1)?.role === "user" && (
              <button
                className="secondary retry-response"
                disabled={active}
                onClick={() => generate(true)}
              >
                <RefreshCw size={14} /> Retry response
              </button>
            )}
          </div>
        </section>
        {!following && messages.length > 0 && (
          <button
            className="scroll-down icon"
            aria-label="Scroll to latest message"
            onClick={scrollDown}
          >
            <ArrowDown size={19} />
          </button>
        )}
        <div className="composer-area">
          {error && (
            <div className="error dismissible" role="alert">
              <span>{error}</span>
              <button
                className="icon"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {context?.near_limit && (
            <div className="context-warning">
              <span>
                Context is {context.estimated ? "approximately " : ""}
                {Math.round(context.percentage)}% full.
              </span>
              <button
                disabled={active}
                onClick={() => {
                  setPopover(null);
                  compact();
                }}
              >
                Compact context
              </button>
            </div>
          )}
          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault();
              generate();
            }}
          >
            {!!files.length && (
              <div className="attachment-previews">
                {files.map(({ id, file, status, progress, error:uploadError }) => (
                  <div key={id}><AttachmentPreview
                    file={file}
                    disabled={active}
                    onRemove={() => removeFile(id)}
                    formatSize={formatSize}
                  /><small role="status">{status==='uploading'?`Uploading ${progress||0}%`:status}{uploadError&&` · ${uploadError}`}</small>{status==='error'&&<button type="button" disabled={active} onClick={()=>startAttachmentUpload(filesRef.current.find(item=>item.id===id))}>Retry {file.name}</button>}</div>
                ))}
              </div>
            )}
            <ChatDatasets key={`${account?.id}-${cid}`} api={api} cid={cid} value={datasetRequests} onChange={setDatasetRequests} disabled={active} refresh={sourceRefresh}/>
            <div className="composer-input">
              <Paperclip size={19} />
              <textarea
                ref={textarea}
                rows={1}
                maxLength={30000}
                aria-label="Message Kumuta AI"
                placeholder="Type a message, or upload a file…"
                value={input}
                disabled={active}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    generate();
                  }
                }}
              />
            </div>
            <div className="composer-toolbar">
              <input
                ref={fileInput}
                type="file"
                multiple
                accept={CHAT_ACCEPT}
                hidden
                onChange={(event) => {
                  addFiles(event.target.files);
                  event.target.value = "";
                }}
              />
              <div className="attachment-tools">
                <button
                  type="button"
                  className={`tool-chip web-search-toggle ${webSearch ? "selected" : ""}`}
                  aria-pressed={webSearch}
                  title="Enable Google Search grounding; availability and charges depend on your model and Google project"
                  onClick={() => setWebSearch((value) => !value)}
                >
                  <Search size={14} /> Web Search{" "}
                  {webSearch && <span className="search-active-dot" />}
                </button>
                <label className="quickui-mode">
                  <Sparkles size={14} />
                  <select
                    aria-label="QuickUI mode for this chat"
                    value={quickuiBehavior}
                    onChange={(e) => setQuickuiBehavior(e.target.value)}
                  >
                    <option value="">
                      QuickUI · {quickuiSettings.preferences.behavior}
                    </option>
                    <option value="automatic">Automatic</option>
                    <option value="prefer">Prefer QuickUI</option>
                    <option value="disabled">Markdown only</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="attach-plus"
                  aria-label="Attach files"
                  disabled={active}
                  onClick={attachAny}
                >
                  <Plus size={19} />
                </button>
                <span
                  className="file-limit"
                  title="Up to 5 files, 8 MB each, 20 MB total. PDFs up to 30 pages."
                >
                  5 files · 8 MB each
                </span>
              </div>
              {busy ? (
                <button
                  type="button"
                  className="send stop"
                  title="Stop generation"
                  aria-label="Stop generation"
                  onClick={() => controller.current?.abort()}
                >
                  <Square size={17} fill="currentColor" />
                </button>
              ) : (
                <button
                  className="send"
                  disabled={active || files.some(item=>item.status!=='ready') || (!input.trim() && !files.length)}
                  title="Send message"
                  aria-label="Send message"
                >
                  <Send size={19} />
                </button>
              )}
            </div>
          </form>
          {!messages.length && <div className="prompt-chips">{['Summarize a document', 'Help me plan my project', 'Explain a tricky concept', 'Brainstorm ideas'].map(text => <button key={text} onClick={() => { setInput(text); textarea.current?.focus(); }}>{text}</button>)}</div>}
          <p className="disclaimer">
            Kumuta AI can make mistakes. Check important information.
            <span> Powered by Gemini.</span>
          </p>
        </div>
      </main>
      </div>
      {modulePicker && <Modal title={`Choose a project for ${tabLabel(modulePicker)}`} onClose={() => setModulePicker(null)}><div className="ws-form"><p>Select a project to keep your work together.</p>{workspaceStore.projects.filter(p => !p.archived).map(p => <button key={p.id} className="context-option" onClick={() => { if (navigate({ screen: 'project', projectId: p.id, tab: modulePicker })) setModulePicker(null); }}>{p.name}</button>)}<button className="primary compact" onClick={() => { setModulePicker(null); workspaceAction('project-create'); }}>Create a project</button></div></Modal>}
      {workspaceDialog && <WorkspaceDialog key={workspaceDialog} type={workspaceDialog} store={workspaceStore} api={api}
        onClose={() => setWorkspaceDialog(null)} onCreated={project => navigate({ screen: 'project', projectId: project.id, tab: 'overview' }, true)}
        onDeleted={() => { setChatProject(p => p?.workspace_id === workspaceStore.workspaceId ? null : p); navigate({ screen: 'projects' }, true); loadHistory(search); }} />}
      {movingChat && <MoveChatDialog conversation={movingChat} api={api} store={workspaceStore} onClose={() => setMovingChat(null)}
        onSaved={(result, project) => {
          if (result.id === cid) { setChatProject(project); setContext(null); }
          if (result.id === cid) { setTutorRequest(null); setSelectedDocuments([]); setDocumentMode('search'); }
          loadHistory(search);
          workspaceStore.refreshProjects();
          if (view.screen === 'project') setView({ ...view, refresh: (view.refresh || 0) + 1 });
        }} />}

      {chatSave&&<ChatSave api={api} {...chatSave} projects={workspaceStore.projects} projectId={chatProject?.id} conversationId={cid} registerGuard={registerGuard} onClose={()=>setChatSave(null)} onSaved={setSavedItem}/>}{documentsOpen && cid && <Modal title="Conversation documents" wide busy={documentBusy} onClose={() => setDocumentsOpen(false)}><DocumentsPanel key={cid} api={api} conversationId={cid} initialSelected={selectedDocuments} onBusy={setDocumentBusy} onAsk={(ids, mode) => { setSelectedDocuments(ids); setDocumentMode(mode); setInput(documentPrompt(mode)); setDocumentsOpen(false); textarea.current?.focus(); }} /></Modal>}
      {documentSource && <DocumentPreview api={api} source={documentSource} onClose={() => setDocumentSource(null)} />}
      {rememberContent !== null && <RememberDialog api={api} projectId={chatProject?.id} conversationId={cid} content={rememberContent} onClose={() => setRememberContent(null)} />}
      {settings && account && (
        <Settings
          projectId={view.screen === 'project' ? view.projectId : chatProject?.id} conversationId={view.screen === 'chat' ? cid : undefined} onFiles={async () => { setSettings(null); if (view.screen === 'project') navigate({ ...view, tab: 'documents' }); else if (chatProject) openModule('documents'); else { try { if (!cid) { const created = await api('/conversations', { method: 'POST', ...jsonBody({ project_id: null }) }); currentId.current = created.id; setCid(created.id); setConversations(previous => [created, ...previous]); } setDocumentsOpen(true); } catch (e) { setError(e.message); } } }}
          tab={settings}
          setTab={setSettings}
          close={closeSettings}
          account={account}
          api={api}
          onAccount={(data) => {
            setAccount(data);
            if (data.has_api_key) loadModels();
          }}
        />
      )}
    </div>
    </QuickUIContext.Provider>
  );
}

createRoot(document.getElementById("root")).render(<App />);
