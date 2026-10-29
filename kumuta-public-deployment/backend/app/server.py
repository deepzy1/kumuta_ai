"""Unified production server serving both Kumuta AI & Canvas SPAs and FastAPI backend."""
import mimetypes
import os
from pathlib import Path
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import FileResponse, Response, PlainTextResponse
# Auto-generate secure random secrets if not provided in environment
if len(os.getenv("JWT_SECRET", "")) < 32:
    import secrets
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)

if not os.getenv("API_KEY_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet
    os.environ["API_KEY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from .main import app as api_app

DIST_DIR = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist")).resolve()
INDEX_HTML = DIST_DIR / "index.html"
CANVAS_HTML = DIST_DIR / "canvas.html"

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
]


class UnifiedApp:
    def __init__(self, inner: ASGIApp, dist_dir: Path):
        self.inner = inner
        self.dist_dir = dist_dir
        self.index_html = dist_dir / "index.html"
        self.canvas_html = dist_dir / "canvas.html"

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "lifespan":
            await self.inner(scope, receive, send)
            return

        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return

        path = scope.get("path", "/")
        method = scope.get("method", "GET")

        # 1. API routes: /api/... or /api -> strip /api prefix and forward to FastAPI
        if path == "/api" or path.startswith("/api/"):
            sub_path = path[4:] if path.startswith("/api/") else "/"
            sub_scope = dict(scope)
            sub_scope["path"] = sub_path
            await self.inner(sub_scope, receive, send)
            return

        # 2. FastAPI direct endpoints (health, ready, swagger docs, openapi schema)
        if path in ("/health", "/ready", "/docs", "/openapi.json", "/redoc"):
            await self.inner(scope, receive, send)
            return

        # 3. Non-GET/HEAD methods without /api prefix -> forward to FastAPI
        if method not in ("GET", "HEAD"):
            await self.inner(scope, receive, send)
            return

        # 4. Frontend static files and SPA routes
        response = self.handle_static_or_spa(path)
        await response(scope, receive, send)

    def handle_static_or_spa(self, path: str) -> Response:
        # Chatbot root
        if path in ("/", "/index.html"):
            return self._serve_html(self.index_html)

        # Canvas root
        if path in ("/canvas", "/canvas/", "/canvas.html"):
            return self._serve_html(self.canvas_html)

        # Static assets (assets, fonts, licenses, svg icons, favicon)
        rel_path = path.lstrip("/")
        try:
            target = (self.dist_dir / rel_path).resolve()
        except Exception:
            return PlainTextResponse("Not Found", status_code=404)

        # Ensure no path traversal outside dist_dir
        if str(target).startswith(str(self.dist_dir)) and target.is_file():
            # Immutable cache for versioned assets
            if path.startswith("/assets/"):
                return FileResponse(
                    target,
                    headers={
                        "Cache-Control": "public, max-age=31536000, immutable",
                        "X-Content-Type-Options": "nosniff",
                        "Referrer-Policy": "no-referrer",
                        "X-Frame-Options": "DENY",
                    },
                )
            # Normal static file
            content_type, _ = mimetypes.guess_type(str(target))
            return FileResponse(
                target,
                media_type=content_type or "application/octet-stream",
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "X-Frame-Options": "DENY",
                },
            )

        # Explicit 404 for missing assets or files with extensions
        if path.startswith(("/assets/", "/fonts/", "/licenses/")) or "." in Path(path).name:
            return PlainTextResponse("File Not Found", status_code=404)

        # SPA fallback routing
        if path.startswith("/canvas"):
            return self._serve_html(self.canvas_html)
        return self._serve_html(self.index_html)

    def _serve_html(self, html_path: Path) -> Response:
        if not html_path.is_file():
            return PlainTextResponse(
                "Frontend assets not found. Run 'npm run build' in frontend directory.",
                status_code=503,
            )
        return FileResponse(
            html_path,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
            },
        )


app = UnifiedApp(api_app, DIST_DIR)
