#!/usr/bin/env bash
# Start the local demo: Postgres (Docker), FastAPI backend (:8010) and Vite frontend (:5173).
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d db
until docker compose exec -T db pg_isready -U paragraf >/dev/null 2>&1; do sleep 1; done

if [ "$(docker compose exec -T db psql -U paragraf -Atc "SELECT to_regclass('provisions') IS NOT NULL AND EXISTS (SELECT 1 FROM provisions WHERE embedding IS NOT NULL)")" != "t" ]; then
  echo "First run: downloading acts and building the index..."
  uv run python -m paragraf.ingest
  uv run python -m paragraf.indexing.index
fi

# --no-proxy-headers: the app reads X-Forwarded-For itself (TRUSTED_PROXY_HOPS)
uv run uvicorn paragraf.api.main:app --port 8010 --no-proxy-headers &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null' EXIT
(cd frontend && [ -d node_modules ] || npm install --no-audit --no-fund)
echo
echo "  Asystent Prawa Pracy → http://localhost:5173"
echo
cd frontend && npx vite --port 5173
