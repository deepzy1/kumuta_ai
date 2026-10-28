import { browserSignIn, watchSession } from '@kumuta/platformSession.js';
import {SharedBoards} from '@kumuta/CanvasSharing.jsx';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { request, jsonBody } from '@kumuta/api.js';
import { allPages } from '@kumuta/workspaceData.js';
import Modal, { Empty, ErrorNotice } from '@kumuta/Modal.jsx';
import Library from './Library.jsx';
import { QuickUIContext, useQuickUISettings } from '@kumuta/QuickUISettings.jsx';
import { canvasAppearance } from '@kumuta/canvasAppearance.js';
import Editor from './Editor.jsx';
import { readRoute, routeHash } from './navigation.js';

export const mainOrigin = import.meta.env.VITE_KUMUTA_APP_URL || (location.pathname==='/canvas.html' ? location.origin : `${location.protocol}//${location.hostname}:5173`);
export function Brand() { return <span className="brand"><span className="brand-mark" aria-hidden="true">K</span><span>Kumuta <b>Canvas AI</b></span></span>; }

function SignIn({ onAuth }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <main className="signin"><Brand /><div className="signin-copy"><span className="eyebrow">A SPACE FOR YOUR IDEAS</span><h1>Make room<br />for your next <em>idea.</em></h1><p>Draw, plan, and connect your thoughts.<br />Your boards, saved in your Kumuta workspace.</p></div>
    <form onSubmit={async e => { e.preventDefault(); const data = new FormData(e.currentTarget); setBusy(true); setError(''); try { await onAuth(await request('', '/auth/login', { method:'POST', ...jsonBody(Object.fromEntries(data)) })); } catch(e) { setError(e.message); } finally { setBusy(false); } }}>
      <h2>Welcome to Canvas</h2><p>Sign in with your existing Kumuta AI account.</p><label>Email address<input name="email" type="email" autoComplete="username" required /></label><label>Password<input name="password" type="password" autoComplete="current-password" required /></label><ErrorNotice error={error} /><button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button><small>Your Kumuta browser session is shared securely on this host.</small><a href={mainOrigin} rel="noreferrer">Open Kumuta AI →</a>
    </form></main>;
}

export default function App() {
  const [token, setToken] = useState('');
  const tokenRef = useRef(token); tokenRef.current = token;
  const [route, setRoute] = useState(() => readRoute(location.hash));
  const current = useRef(route), guard = useRef(async () => true);
  const [workspaces, setWorkspaces] = useState([]), [error, setError] = useState(''), [loading, setLoading] = useState(false), [attempt, setAttempt] = useState(0);
  const [account,setAccount]=useState(null),[checking,setChecking]=useState(true);
  const [expired, setExpired] = useState(false), [authDialog, setAuthDialog] = useState(false);
  const api = useCallback(async (path, options) => {
    try { return await request(tokenRef.current, path, { ...options, signal: options?.signal || AbortSignal.timeout(20000) }); }
    catch (e) { if (e.status === 401) setExpired(true); throw e; }
  }, []);
  const navigate = useCallback(async next => {
    if (!await guard.current()) return;
    current.current = next; setRoute(next); location.hash = routeHash(next);
  }, []);
  const registerGuard = useCallback(fn => { guard.current = fn; return () => { if (guard.current === fn) guard.current = async () => true; }; }, []);
  useEffect(() => {
    const changed = async () => {
      const next = readRoute(location.hash), before = current.current;
      if (JSON.stringify(next) === JSON.stringify(before)) return;
      if (await guard.current()) { current.current = next; setRoute(next); }
      else history.replaceState(null, '', routeHash(before));
    };
    window.addEventListener('hashchange', changed); return () => window.removeEventListener('hashchange', changed);
  }, []);
  useEffect(() => {
    if (!token || checking) return;
    let active = true; const abort = new AbortController(); setLoading(workspaces.length === 0); setError('');
    allPages(api, '/workspaces', { signal: abort.signal }).then(rows => { if (active) setWorkspaces(rows); }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; abort.abort(); };
  }, [api, token, attempt, checking]);
  const authenticate = async credentials => { const result=await browserSignIn(credentials); setAccount(result); setChecking(false); sessionStorage.setItem('kumuta.canvas.token', result.token); setExpired(false); setAuthDialog(false); setToken(result.token); };
  const logout = async () => { if (!await guard.current()) return; await request('', '/auth/logout', {method:'POST'}); sessionStorage.removeItem('kumuta.canvas.token'); sessionStorage.removeItem('token'); setToken(''); setAccount(null); setWorkspaces([]); };
  useEffect(()=>{
    let active=true;
    const start=async()=>{
      try{
        let account=await request('','/auth/session');
        if(!account.authenticated){
          const legacy=sessionStorage.getItem('kumuta.canvas.token');
          if(!legacy||legacy==='cookie')return;
          account=await request(legacy,'/auth/me');
          await browserSignIn({token:legacy});
        }
        if(active){setAccount(account);sessionStorage.setItem('kumuta.canvas.token','cookie');setToken('cookie');}
      }catch(e){if(active&&e.status===401){setToken('');setAccount(null);setExpired(false);}}
      finally{if(active)setChecking(false);}
    };start();return()=>{active=false;};
  },[]);
  useEffect(()=>{
    if(!token||!account)return;
    return watchSession(path=>request(tokenRef.current,path),next=>{
      if(next.id!==account.id){setAccount(next);setWorkspaces([]);setAttempt(n=>n+1);setExpired(false);}
    },()=>setExpired(true));
  },[token,account?.id]);
  const quickUI=useQuickUISettings(api,token?`${token}:${account?.id||''}`:'');
  const [systemDark,setSystemDark]=useState(()=>matchMedia('(prefers-color-scheme: dark)').matches);
  useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const update=()=>setSystemDark(media.matches);media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
  const appearance=canvasAppearance(quickUI.preferences,systemDark);
  const appearanceKey=JSON.stringify(appearance.vars);
  useEffect(()=>{
    const root=document.documentElement;
    const previous=Object.fromEntries(Object.keys(appearance.vars).map(key=>[key,root.style.getPropertyValue(key)]));
    Object.entries(appearance.vars).forEach(([key,value])=>root.style.setProperty(key,value));
    return()=>Object.entries(previous).forEach(([key,value])=>value?root.style.setProperty(key,value):root.style.removeProperty(key));
  },[appearanceKey]);
  if(checking)return <p className="page-message" role="status">Checking your Kumuta session…</p>;
  if (!token) return <SignIn onAuth={authenticate} />;
  return <QuickUIContext.Provider value={{...quickUI,canvasAppearance:appearance}}><div key={account?.id} className={`canvas-app canvas-density-${appearance.widget.density}`} data-appearance={appearance.widget.appearance} style={appearance.vars}>
    {route.boardId ? <Editor key={`${account?.id}-${route.boardId}`} api={api} id={route.boardId} workspaces={workspaces} navigate={navigate} registerGuard={registerGuard} accountId={account?.id} /> : <>
      <header className="platform-header"><Brand /><nav aria-label="Products"><span className="active-nav">Boards</span><a href={mainOrigin} rel="noreferrer">Kumuta AI ↗</a></nav><button onClick={logout}>Sign out</button></header>
      {loading ? <p className="page-message" role="status">Loading your workspaces…</p> : error ? <div className="page-message"><ErrorNotice error={error} retry={() => setAttempt(n=>n+1)} /></div> : workspaces.length ? <Library key={`${account?.id}-${token}`} api={api} route={route} workspaces={workspaces} navigate={navigate} onRefresh={() => setAttempt(n=>n+1)} /> : <Empty title="No workspaces available">Create a workspace in Kumuta AI to start a board.</Empty>}
      <SharedBoards api={api} navigate={navigate}/>
    </>}
    {expired && <div className="session-alert" role="alert">Your session expired. Pending drawings remain in this editor. <button onClick={() => setAuthDialog(true)}>Sign in again</button></div>}
    {authDialog && <Modal title="Renew Canvas session" onClose={() => setAuthDialog(false)}><SignIn onAuth={authenticate} /></Modal>}
  </div></QuickUIContext.Provider>;
}
