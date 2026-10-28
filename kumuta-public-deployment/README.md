# Kumuta AI + Excalidraw Canvas Unified Deployment

This repository contains the standalone, Dockerized deployment bundle for **Kumuta AI** (conversational AI, document RAG, dataset analysis, QuickUI, study/focus tools) and **Kumuta Canvas AI** (full-viewport Excalidraw whiteboard with diagram generation and interactive widgets).

Both applications and the unified FastAPI ASGI backend are packaged into **ONE Docker container** designed to run seamlessly on Render's free tier or any container hosting platform using a single public URL and a single exposed HTTP port (`$PORT`).

---

## 1. System Architecture

### Original Codebase Services (Discovered Architecture)
Before unification, the workspace consisted of:
1. **Kumuta AI Frontend** (`React 18 / Vite 5 / TypeScript`):
   - Conversational chat interface, markdown/LaTeX streaming, document upload & RAG, CSV/Excel dataset analytics, flashcard study modes, and QuickUI micro-apps.
   - Communicates with `/api/*` endpoints.
2. **Kumuta Canvas AI (Excalidraw)** (`React 18 / Vite 8 / @excalidraw/excalidraw 0.18.1`):
   - Whiteboard drawing editor supporting diagrams, frames, QuickUI widgets, AI generation jobs, and board libraries.
   - Built with same-origin API assumptions and shares the browser session with Kumuta AI.
3. **Kumuta FastAPI Backend** (`Python 3.12 / FastAPI / SQLAlchemy 2 / SQLite`):
   - Powers all REST and Server-Sent Event (SSE) streaming routes for authentication (`/auth/*`), conversations (`/conversations/*`), documents (`/documents/*`), datasets (`/datasets/*`), workspaces (`/workspaces/*`), QuickUI (`/quickui/*`), focus/study (`/study/*`, `/focus/*`), and whiteboard boards (`/boards/*`, `/boards/{bid}/generation`, `/boards/{bid}/intelligence`).
   - Runs asynchronous background workers for document extraction, dataset processing, and canvas AI generation.

### Unified Single-Container Architecture
In this deployment:
```
                                Render Public HTTPS URL
                                           │
                                           ▼
                 ┌──────────────────────────────────────────────────┐
                 │       Unified Docker Web Service (PORT=$PORT)     │
                 │                                                  │
                 │   Uvicorn Production ASGI Server (app.server)    │
                 │                         │                        │
                 ├─────────────────────────┼────────────────────────┤
                 │                         │                        │
    ┌────────────┴────────────┐            │         ┌──────────────┴──────────────┐
    │     Static SPAs         │            │         │      FastAPI Backend        │
    │                         │            │         │                             │
    │  • /         (Kumuta AI)│            │         │  • /health & /ready         │
    │  • /canvas/  (Canvas)   │            │         │  • /docs & /openapi.json    │
    │  • /assets/* (Hashed JS)│            │         │  • /api/* (Rewritten to     │
    │  • /fonts/*  (Excalidraw│            │         │    internal FastAPI routes) │
    │  • SPA fallback routing │            │         │                             │
    └─────────────────────────┘            │         └──────────────┬──────────────┘
                                           │                        │
                                           ▼                        ▼
                                ┌──────────────────────────────────────┐
                                │     In-Memory / Non-Root Storage     │
                                │   • SQLite: /data/db/chat.db         │
                                │   • Documents: /data/documents       │
                                └──────────────────────────────────────┘
```

- **Frontend Compilation**: Multi-stage Docker build compiles both Kumuta AI (`index.html`) and Kumuta Canvas (`canvas.html`) into static production bundles sharing assets and font definitions.
- **Unified Routing**:
  - `/` serves the Kumuta AI Chatbot SPA.
  - `/canvas`, `/canvas/`, and `/canvas.html` serve the Kumuta Canvas AI SPA.
  - `/api/...` routes directly to the FastAPI endpoints by stripping the `/api` prefix at the ASGI layer.
  - `/health` and `/ready` provide container health checks.
  - `/docs` serves interactive OpenAPI Swagger documentation.
  - Nested browser routes (e.g., `/workspace/project-1` or `/canvas/board/2`) correctly fall back to their respective SPAs on browser refresh.
- **Shared Authentication**: HttpOnly `kumuta_session` cookies and Bearer tokens are shared seamlessly across both applications on the single origin.

---

## 2. Local Docker Instructions

### Prerequisites
- Docker (or Docker Desktop) installed.
- (Optional) Python 3.12+ or Node.js 20+ for local non-container testing.

### Build and Run Locally
1. **Clone or navigate to this folder**:
   ```bash
   cd kumuta-public-deployment
   ```

2. **Build the Docker image**:
   ```bash
   docker build -t kumuta-unified:latest .
   ```

3. **Run the container**:
   ```bash
   docker run -d --name kumuta-app -p 8000:8000 \
     -e PORT=8000 \
     -e JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))") \
     -e API_KEY_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
     -e KUMUTA_ENV=development \
     kumuta-unified:latest
   ```

4. **Verify running endpoints**:
   - Kumuta AI Chatbot: [http://localhost:8000/](http://localhost:8000/)
   - Kumuta Canvas Whiteboard: [http://localhost:8000/canvas/](http://localhost:8000/canvas/)
   - API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Health Probe: [http://localhost:8000/health](http://localhost:8000/health)

5. **Stop and remove container**:
   ```bash
   docker stop kumuta-app && docker rm kumuta-app
   ```

---

## 3. GitHub Setup Instructions

To push this project to your own new GitHub repository:

```bash
cd "/home/deepak/Music/Project Kumuta Rama/kumuta-public-deployment"

# 1. Initialize git in this standalone folder
git init -b main

# 2. Stage all deployment files
git add .

# 3. Create initial commit
git commit -m "feat: standalone dockerized deployment of Kumuta AI and Excalidraw Canvas"

# 4. Create your new empty GitHub repository (via GitHub web UI or gh cli):
# gh repo create kumuta-public-deployment --public --source=. --remote=origin

# Or manually add your GitHub remote URL and push:
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

*(Note: None of your existing local git repositories or parent folders will be affected.)*

---

## 4. Render Deployment Step-by-Step

### 1. Create a New Web Service
1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** → **Web Service**.
3. Select **Build and deploy from a Git repository**.
4. Connect and select your newly created GitHub repository (`kumuta-public-deployment`).

### 2. Configure Service Settings
- **Name**: `kumuta-ai` (or your preferred name; this forms your URL: `https://kumuta-ai.onrender.com`).
- **Region**: Choose the closest region (e.g., Oregon, Frankfurt, Singapore).
- **Branch**: `main`.
- **Root Directory**: Leave blank (uses repository root).
- **Runtime**: **Docker**.
- **Instance Type**: **Free** (0.1 CPU, 512 MB RAM).

### 3. Configure Environment Variables
Under the **Environment Variables** tab, add:

| Variable | Value / Description | Required |
|---|---|---|
| `JWT_SECRET` | A secure random string (≥ 32 chars). Generate with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` | **Yes** |
| `API_KEY_ENCRYPTION_KEY` | A Fernet key. Generate with: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | **Yes** |
| `KUMUTA_ENV` | `development` (enables user signup in the public demo) | **Yes** |
| `KUMUTA_ALLOW_REGISTRATION` | `true` | Recommended |
| `CANVAS_DAILY_JOBS` | `30` (or `0` to disable the rate limit) | Optional |

> **Note on PORT**: Do NOT manually set `PORT=8000` on Render. Render automatically injects `PORT` (usually `10000`). The container entrypoint automatically uses `$PORT` provided by Render.

> **Note on CORS**: You do NOT need to configure cross-origin settings because both frontend applications and the API are served from the **exact same public URL**.

### 4. Deploy
1. Click **Create Web Service**.
2. Render will trigger the multi-stage Docker build, compile the frontends, install backend dependencies, and launch Uvicorn.
3. Once live, open your Render URL:
   - Chatbot: `https://your-service-name.onrender.com/`
   - Canvas: `https://your-service-name.onrender.com/canvas/`

---

## 5. Storage, Quotas, and Security Notes

### Ephemeral Storage (Render Free Tier)
- Render's free tier uses an **ephemeral disk**.
- SQLite database (`/data/db/chat.db`) and uploaded documents (`/data/documents`) are stored within the container filesystem.
- When Render restarts the container (e.g., after 15 minutes of inactivity or upon redeployment), the filesystem resets to the clean state.
- **For a permanent production database**: Connect a free managed PostgreSQL database or attach a persistent disk (Render disk requires a paid tier).

### Bring Your Own Key (BYOK) Model
- No shared Google Gemini API key is bundled into this Docker container.
- Each user inputs their own Gemini API key inside **Settings → My API Key** in the UI.
- Keys are encrypted in SQLite using your server's `API_KEY_ENCRYPTION_KEY` via Fernet encryption and are never exposed in browser bundles or client source code.

### Rate Limiting & Sleep Behavior
- **Free Tier Inactivity**: Render free instances spin down after 15 minutes of inactivity. The first request after a sleep period may take 30–50 seconds to boot.
- **Daily Quotas**: Canvas jobs have a default rolling limit configured via `CANVAS_DAILY_JOBS` to prevent quota abuse.

---

## 6. Troubleshooting

- **Container fails with `Set JWT_SECRET to a random string of at least 32 characters`**:
  - Ensure `JWT_SECRET` is defined in Render environment variables with at least 32 characters.
- **Container fails with `Set API_KEY_ENCRYPTION_KEY to a Fernet key`**:
  - Ensure `API_KEY_ENCRYPTION_KEY` is a valid 32-byte base64 Fernet key generated using cryptography.
- **Browser returns 403 `Browser session requires a trusted Origin and CSRF header`**:
  - The API expects requests from the same origin or origins declared in `CORS_ORIGINS`. Ensure you access the app via the configured domain.
- **API calls return 428 `Precondition Required`**:
  - This is expected when a newly registered user has not yet entered their Gemini API key. Go to **Settings → My API Key** in the chatbot to save your key.
