# ==============================================================================
# Stage 1: Build the unified frontend assets (Chatbot + Excalidraw Canvas)
# ==============================================================================
FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /build

# 1. Install Excalidraw Canvas dependencies
COPY canvas/package.json canvas/package-lock.json ./canvas/
COPY canvas/scripts/ ./canvas/scripts/
RUN cd canvas && npm ci

# 2. Copy Canvas source code
COPY canvas/ ./canvas/

# 3. Install main frontend dependencies
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# 4. Copy main frontend source code and compile production bundle
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# ==============================================================================
# Stage 2: Production Python runtime image
# ==============================================================================
FROM python:3.12-slim-bookworm AS runtime

# Install minimal runtime dependencies (ca-certificates, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Create a non-root runtime user and group
RUN groupadd -g 1000 kumuta && \
    useradd -u 1000 -g kumuta -m -s /bin/bash kumuta

# Create directory structure for code and persistent SQLite/document storage
WORKDIR /app
RUN mkdir -p /data/db /data/documents /app/frontend/dist && \
    chown -R kumuta:kumuta /data /app

# Install Python backend dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend application code
COPY backend/ /app/backend/

# Copy compiled frontend production assets from Stage 1
COPY --from=frontend-builder /build/frontend/dist/ /app/frontend/dist/

# Ensure all application and data files are owned by the non-root user
RUN chown -R kumuta:kumuta /app /data

# Default production environment settings
ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    KUMUTA_ENV=development \
    DATABASE_URL=sqlite:////data/db/chat.db \
    DOCUMENT_STORAGE_DIR=/data/documents \
    FRONTEND_DIST=/app/frontend/dist \
    JWT_SECRET=default_demo_jwt_secret_render_production_32chars \
    API_KEY_ENCRYPTION_KEY=EdhgCI45B2amJZT9q0_aVzxw-uuagbbtctevvKWg1kg=

# Switch to the non-root user
USER kumuta
WORKDIR /app/backend

# Expose default port
EXPOSE 8000

# Health check probe against /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://127.0.0.1:${PORT:-8000}/health || exit 1

# Start production Uvicorn server binding to 0.0.0.0 and $PORT
CMD ["sh", "-c", "exec uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
