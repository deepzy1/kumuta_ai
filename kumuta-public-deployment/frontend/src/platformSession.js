import {request} from './api.js';
export const canvasURL = (workspaceId,projectId) => `${import.meta.env.VITE_CANVAS_URL || '/canvas.html'}#/library?${new URLSearchParams({...(workspaceId?{workspace:workspaceId}:{}),...(projectId?{project:projectId}:{})})}`;
export async function browserSignIn(result) {
  await request(result.token,'/auth/browser-session',{method:'POST'});
  return {...result,token:'cookie'};
}
// Only checks server identity. No credential broadcasts or cross-origin storage.
export function watchSession(api,onIdentity,onExpired) {
  let active=true,busy=false;
  const check=async()=>{if(busy||!active)return;busy=true;try{const account=await api('/auth/me');if(active)onIdentity(account);}catch(e){if(active&&e.status===401)onExpired();}finally{busy=false;}};
  const timer=setInterval(check,5000);window.addEventListener('focus',check);check();
  return()=>{active=false;clearInterval(timer);window.removeEventListener('focus',check);};
}
