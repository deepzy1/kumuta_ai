# Kumuta Canvas AI

## D7-8 platform integration and sharing

The main application now builds `/canvas.html` from this actual editor source, with a same-origin `/api` proxy and shared revocable HttpOnly browser session. Use **Project → Canvas Boards**, the Canvas sidebar link or an authorized board deep link. Share with an existing account as Editor/Viewer after reviewing saved content and history; recipients accept in **Shared with me**. Original sources and personal chat/proposal history remain private. Editors use their own Gemini key/quota; viewers can interact with supported widgets locally without saving. No real-time multiplayer or public links.

Current backend schema head is **22**, applied through the existing backed-up additive migration runner. Existing boards stay private. The complete policy, migration/test evidence and screenshots are in `../mini_llm/gemini-chatbot-mvp/gemini-chatbot/D-docs/Kumuta_Canvas_AI_D7-8_Platform_Integration_Sharing_BYOK.md`. No dependencies or licenses were changed; WebP and baseline licensing/release gates remain as documented.

The existing React 18.3.1 / Excalidraw 0.18.1 client on port 5174 now opens a persistent board library. It reuses the Kumuta API client, pagination helper, accessible modal and FastAPI board APIs. D7-3 adds manual native diagrams, controlled QuickUI widgets and scriptless HTML/CSS previews. D7-4 adds a functional AI sidebar using the shared Gemini gateway, durable SQLite jobs/SSE and immutable artifact lifecycle in the existing backend. No new application dependencies or separate backend/provider service.

## AI generation and artifact versions

Open **Board details → AI** to generate native editable diagrams or structured interactive widgets. Use the existing Kumuta key/model settings, then **Generate → Preview result → Insert into canvas**. Regenerate appends a preview version; applying/reverting is explicit. Duplicate/remove are local operations with no model calls. Job progress/history survive refresh; a failed regeneration preserves the inserted output. Custom execution/simulations remain disabled by the sandbox security gate. Each explicit generation/retry may consume Gemini quota; no automatic provider retries occur.

D7-4 originally introduced schema 15 using the established backed-up additive migration runner. Restart the existing backend to load routes/worker. For contracts, limits, rollback, test evidence and screenshots, see `../mini_llm/gemini-chatbot-mvp/gemini-chatbot/D-docs/Kumuta_Canvas_AI_D7-4_AI_Generation_Artifact_Lifecycle.md`. Existing license/font release gates remain; no real-provider smoke test is claimed.

## Local development

Use Node 20.19+ (the installed runtime is `~/.nvm/versions/node/v20.19.2/bin/node`). Start the existing Kumuta FastAPI backend on port 8000, then from this directory:

```bash
npm run dev
```

Open `http://localhost:5174`. An existing Kumuta browser session on the same hostname is reused; otherwise sign in with the existing account. Keep localhost/127.0.0.1 consistent. The main app on port 5173 creates accounts/workspaces/projects and provides the integrated Canvas entry. Legacy origin-scoped bearer sessions transition to the shared browser session without token-bearing links.

The default `/api` route proxies to `http://127.0.0.1:8000` in Vite. Override the server-only target with `CANVAS_API_PROXY_TARGET`. No JWT is put in URLs, window messages, iframes or generated UI. Existing backend CORS configuration stays unchanged. `VITE_API_URL` may opt into a direct API origin, but that deployment must explicitly allow its exact Canvas origin in backend CORS. Never use a wildcard or put secrets in `VITE_` variables.

The client imports shared modules from `../mini_llm/gemini-chatbot-mvp/gemini-chatbot/frontend/src` through `@kumuta`. Keep the two checkouts in this monorepo layout. `KUMUTA_MAIN_FRONTEND` can override the shared source path when verifying an isolated copy. React is deduplicated to the existing Canvas installation.

## Build / serve

```bash
npm test
npm run build
npm run preview
```

Serve `dist/` with a same-origin `/api/` reverse proxy to the existing backend in production, preserving Authorization, Cookie, Host and the original HTTPS scheme. Example nginx location (inside the Canvas server block):

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Use HTTPS for production frontend/API traffic. This session verifies local Chromium, not deployment configuration. No production config was installed.

## Saving and recovery

Autosave debounces for one second, serializes requests, coalesces edits and uses `expected_revision`. Navigation waits for pending saves. On failure, leaving requires explicit confirmation. Browsers may terminate tabs before a request finishes: beforeunload warns for unsaved changes, and visibility changes attempt a flush; neither promises a successful final save. No scene is automatically stored in local/session storage.

409 conflicts never overwrite newer server data. Download an `.excalidraw` recovery file, explicitly discard/reload, or save a separate recovery board. A lost response may mean the server committed: a retry with the old revision safely becomes a conflict. Retry never silently updates the expected revision. Storage and validation failures retain the local drawing and offer explicit retry/recovery. Keep the tab open until saved.

History restore requires confirmation and creates a new server revision. Archived boards/projects use native view mode; restore an archived project in Kumuta AI. Native keyboard shortcuts require editor focus, as in Excalidraw. Pan/zoom/selection/tool state is transient; D7-1 persists only supported drawing settings. Image files must be inline PNG/JPEG/WebP/GIF. Unsupported embeds/custom elements cannot save; embeddable content rendering is disabled.

Search/sort covers loaded library results. Load more advances by API row count, deduplicates IDs, and preserves the selected workspace/project/status. The offset API offers no snapshot guarantee during concurrent library edits; Refresh reloads the current collection. Sidebar conversations/resources are the existing board-scoped lists; AI generation uses the shared personal key/model configuration and explicit Preview/Accept workflow.

## Verification and licensing

The completion report, test commands, screenshots and exact dependency/font inventory are in `../mini_llm/gemini-chatbot-mvp/gemini-chatbot/D-docs/Kumuta_Canvas_AI_D7-2_Canvas_Library_Editor.md`.

Reuse of the installed Excalidraw is explicitly within this D7-2 session's scope. It does **not** establish commercial clearance. The exact lockfile and existing copied fonts still have unresolved strict MIT/Apache policy and notice/provenance findings. No dependency version, lockfile, copied font or third-party implementation was added or replaced. Resolve release clearance before distribution or expanding incorporation.

## D7-3 manual renderers

Use **Add to canvas** for flowchart/mind-map/architecture examples, charts, tables, cards, calculators, checklists, timelines, progress or an isolated HTML/CSS preview. Paste a bounded manual A/B/C specification or edit widget data through **Widget options**. All example values are illustrative. **Canvas** mode uses the native rectangle for movement/resize; **Interact** enables local controls. Widget options support duplicate with current state, position/size, front/back, lock and delete. Widgets must stay ungrouped, outside frames and unrotated.

Definitions and supported local state persist through existing owned scenes/autosave/recovery/history. Older scene-only clients cannot silently strip definitions. Native undo covers diagram/rectangle operations; widget data/state edits use board revisions. Use **Duplicate widget** for a full copy. Native Load Scene is unavailable on boards with widgets; native image exports include drawing elements rather than rendered overlays. Recovery downloads contain definitions, but native import does not reconstruct them; composite export/import is deferred.

Executable custom JavaScript, a host bridge, maps/3D and all live AI generation/agent streaming remain disabled/deferred. Engine C is an opaque scriptless preview with no network/storage/host access. No remote MCP server or new credentials are required. Existing unresolved D7-2 license/font findings remain release gates.

Full upstream revision review, manual contracts, limits, evidence and D7-4 handoff: `../mini_llm/gemini-chatbot-mvp/gemini-chatbot/D-docs/Kumuta_Canvas_AI_D7-3_Renderer_Foundation.md`.
