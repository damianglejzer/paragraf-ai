# Backend image: FastAPI + agent. The frontend is deployed separately (Vercel).
#
#   docker build -t paragraf-api .
#   docker run --rm -p 8000:8000 -e DATABASE_URL=... -e OPENAI_API_KEY=... paragraf-api
#
# Secrets are never baked in: they come from environment variables at run time
# (.dockerignore keeps .env out of the build context).

# ---- Stage 1: install dependencies into a virtualenv --------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, in their own layer: rebuilt only when pyproject.toml or uv.lock change,
# not on every code edit. --frozen installs exactly the versions pinned in uv.lock.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the code, and the project itself (editable: it points at /app/backend, which keeps
# the repo layout that config.REPO_ROOT relies on).
COPY backend/paragraf ./backend/paragraf
RUN uv sync --frozen --no-dev

# ---- Stage 2: runtime image (no uv, no build caches) --------------------------------------
FROM python:3.12-slim

# Run as an unprivileged user; only the cache directory is writable.
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/backend ./backend
COPY evals/results/latest.json ./evals/results/latest.json
RUN mkdir -p data/cache && chown -R app:app data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8000
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"

# One worker: the per-minute limiter and the concurrency cap live in memory.
# --no-proxy-headers: the app reads X-Forwarded-For itself (TRUSTED_PROXY_HOPS).
CMD ["sh", "-c", "exec uvicorn paragraf.api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-proxy-headers"]
