import { errorMessage } from "./stream";
import { rasterizeSceneFiles } from './canvasSceneFiles.js';
export { readEvents } from "./stream";

export const API = import.meta.env.VITE_API_URL || '/api';
export const authHeaders = token => ({'X-Kumuta-CSRF':'1', ...(token && token !== 'cookie' ? {Authorization:`Bearer ${token}`} : {})});

export async function request(token, path, options = {}) {
  if (options.onUploadProgress) return uploadRequest(token, path, options);
  const { responseType, ...fetchOptions } = options;
  if (/^\/boards\/\d+\/scene$/.test(path) && options.method === 'PUT' && typeof options.body === 'string') {
    const payload = JSON.parse(options.body);
    if (Object.values(payload.scene?.files || {}).some(file => file?.mimeType === 'image/svg+xml')) {
      payload.scene = await rasterizeSceneFiles(payload.scene);
      fetchOptions.body = JSON.stringify(payload);
    }
  }
  let response;
  try {
    response = await fetch(`${API}${path}`, {
      ...fetchOptions,
      credentials: 'include',
      headers: {
        ...options.headers,
        ...authHeaders(token),
      },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Cannot reach Kumuta AI. Check your connection and that the backend is running.",
    );
  }
  if (response.ok && responseType === 'blob') return response.blob();
  if (response.ok && responseType === 'stream') return response;
  const data = await response.json().catch(error => {
    // A cancelled body read must not become a successful empty job snapshot.
    if (error.name === 'AbortError') throw error;
    if (response.ok) throw new Error('Kumuta AI returned an unreadable response. Refresh saved state and try again.');
    return {};
  });
  if (!response.ok) {
    const error = new Error(errorMessage(data, response.status));
    error.status = response.status;
    throw error;
  }
  return data;
}

function uploadRequest(token, path, options) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || 'POST', `${API}${path}`);
    xhr.withCredentials = true;
    xhr.timeout = 60000;
    for (const [key,value] of Object.entries(authHeaders(token))) xhr.setRequestHeader(key,value);
    for (const [key, value] of Object.entries(options.headers || {})) xhr.setRequestHeader(key, value);
    xhr.upload.onprogress = event => { if (event.lengthComputable) options.onUploadProgress(Math.round(100 * event.loaded / event.total)); };
    const abort = () => xhr.abort();
    const cleanup = () => options.signal?.removeEventListener('abort', abort);
    xhr.onload = () => {
      cleanup(); let data;
      try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else { const e = new Error(errorMessage(data, xhr.status)); e.status = xhr.status; reject(e); }
    };
    xhr.onerror = xhr.ontimeout = () => { cleanup(); reject(new Error('Document upload interrupted. Check your connection and retry.')); };
    xhr.onabort = () => { cleanup(); reject(new DOMException('Upload cancelled', 'AbortError')); };
    if (options.signal?.aborted) { reject(new DOMException('Upload cancelled', 'AbortError')); return; }
    options.signal?.addEventListener('abort', abort, { once: true });
    xhr.send(options.body);
  });
}

export const jsonBody = (data) => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
