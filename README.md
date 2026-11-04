# Paragraf AI

An AI assistant for Polish labour law, built on **the full Labour Code (Kodeks pracy)**. It
**always cites the exact article / § / paragraph** and then
**automatically verifies every citation**. The verifier checks that the provision exists, that
the quoted fragment is really in it, and that it supports the claim. The chat is the surface; the
point of the project is retrieval quality and citation verification.

> Portfolio project. Not legal advice. LLM calls use the OpenAI API (cheap mini/nano models);
> embeddings and reranking use Jina's free tier.

## What it does

- **Structural chunking** of official consolidated texts from the Sejm ELI API. One chunk is an
  article, § or paragraph, stored with its full path, e.g. `KP, Dział VII, Rozdział I, art. 154 § 1`.
  The parser matches the API's `/struct` tree 100%.
- **Hybrid retrieval.** Lemmatized full-text search (spaCy `pl`, Postgres `simple` config) and
  pgvector embeddings, fused with RRF. Before searching, an LLM rewrites the question into
  statutory vocabulary. A cross-encoder reranks the results.
- **LangGraph agent.** It asks for clarification, refuses out-of-scope questions, looks up cited
  articles and follows cross-references ("art. 22 § 1" → relation).
- **Citation verification.** Each citation gets one of three statuses: *verified*, *uncertain* or
  *wrong*. Wrong citations are removed from the answer. The UI shows the status of every citation.
- **MCP server** (official Python SDK). It exposes `search_law`, `get_article`,
  and `follow_reference`.
- **Demo protection.** Per-IP limits per minute and per day, a global daily budget with a
  cache-only fallback, a cap on concurrent agent runs, an answer cache, request size limits,
  security headers and a proxy-aware client IP that cannot be spoofed (docs/DECISIONS.md, D19).

## Run locally

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cp .env.example .env          # then fill in OPENAI_API_KEY and JINA_API_KEY (Jina is free)
./scripts/dev.sh              # Postgres + API (:8010) + frontend (:5173)
```

Open http://localhost:5173. The first run downloads the acts from the ELI API and builds the
index, which takes about a minute.

Optional: precompute the example questions so they answer instantly (with the API running):

```bash
uv run python -m paragraf.api.warm_cache
```

Free keys:
- OpenAI: https://platform.openai.com/api-keys
- Jina: https://jina.ai (a new key comes with 10M free tokens)

### Step by step (instead of `dev.sh`)

```bash
docker compose up -d db
uv sync
uv run python -m paragraf.ingest            # ELI API -> parse -> Postgres
uv run python -m paragraf.indexing.index    # lemmas + embeddings
uv run uvicorn paragraf.api.main:app --port 8010 --no-proxy-headers
cd frontend && npm install && npm run dev
```

### Evaluation

```bash
uv run python -m paragraf.evaluation.generate   # ~32 synthetic questions, ~70 LLM calls
uv run python -m paragraf.evaluation.run_all    # retrieval + generation, writes frontend/src/data/eval-report.json
```

The suite is deliberately small: `run_all` makes roughly 200 LLM calls (a few cents with the
mini/nano models) and runs 4 questions in parallel. LLM responses are cached on disk, so a re-run only pays for unfinished calls. The
results appear on the "Jak to działa" page.

### Portable bundle (whole app in Docker)

Database with the indexed corpus, backend and frontend as three containers, packed into one file
you can copy to another machine (e.g. on a USB drive):

```bash
./scripts/bundle.sh            # needs the local db running; writes bundle/ (~375 MB)
```

On the other machine (Docker and internet access needed): `docker load -i
paragraf-images.tar.gz`, put a `.env` with your keys next to `docker-compose.yml`, then
`docker compose up -d` and open http://localhost:8080. Details are in `bundle/README.txt`.
No secrets go into the images; the database starts from a dump of your local one.

### MCP server

```bash
uv run python -m paragraf.mcp_server.server          # stdio (Claude Desktop / Claude Code)
uv run python -m paragraf.mcp_server.server --http   # streamable HTTP on :8765
```

## Deployment

The backend is a single FastAPI process; the frontend is a static Vite build.

**Database.** Postgres 16 with pgvector (e.g. Neon's free tier). Point `DATABASE_URL` at it and,
once, from your machine:

```bash
uv run python -m paragraf.ingest            # tables + the full Labour Code and other acts
uv run python -m paragraf.indexing.index    # lemmas + embeddings (about 2 minutes)
```

**Backend** (e.g. a Render web service, repository root). The repository has a `Dockerfile`:
choose the Docker runtime and Render builds the image itself (no build or start command
needed; it listens on `$PORT`). Locally:

```bash
docker build -t paragraf-api .
docker run --rm --network host -e PORT=8020 -v "$PWD/.env:/app/.env:ro" paragraf-api
```

(Mounting `.env` keeps its inline comments working; `--env-file` would pass them as part of the
values.) Without Docker, on a native Python runtime:
- Build: `uv sync --frozen --no-dev`
- Start: `uv run uvicorn paragraf.api.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers`
  (one worker: the per-minute limiter and the concurrency cap live in memory;
  `--no-proxy-headers`: the app reads `X-Forwarded-For` itself, see `TRUSTED_PROXY_HOPS`)
- Environment: everything from `.env.example`, in particular `OPENAI_API_KEY`, `JINA_API_KEY`,
  `LLM_PROVIDER=openai`, `EMBEDDING_PROVIDER=jina`, `RERANKER_PROVIDER=jina`,
  `CORS_ORIGINS=https://<frontend-domain>` and `TRUSTED_PROXY_HOPS=1` (one proxy in front).
- Check: `curl https://<backend-domain>/api/health` returns `{"status": "ok", "chunks": 1378}`.
- Pre-answer the example questions so they work instantly and for free:
  `uv run python -m paragraf.api.warm_cache --url https://<backend-domain>`

**Frontend** (e.g. Vercel): root directory `frontend`, build `npm run build`, output `dist`,
environment `VITE_API_URL=https://<backend-domain>`. `frontend/vercel.json` adds a Content
Security Policy and the other security headers.

**Spending cap.** Set a monthly budget limit in the OpenAI dashboard. The app's limits keep costs
around a dollar a day at worst, but the provider-side cap is the one nothing can route around.

## Stack

| Layer | Choice |
|---|---|
| Data | Sejm ELI API (HTML consolidated texts), Pydantic validation, on-disk cache |
| DB | PostgreSQL 16 + pgvector (Docker locally) |
| Retrieval | spaCy `pl_core_news_sm` lemmas → `tsvector('simple')`, Jina v3 embeddings, RRF, Jina reranker |
| LLM | OpenAI `gpt-5.4-mini` (answers) and `gpt-5.4-nano` (citation judge) behind a provider interface (`.env`); Gemini still supported |
| Agent | LangGraph |
| API | FastAPI + Server-Sent Events |
| Frontend | React + TypeScript + Vite |
| Observability | Langfuse (optional, via `.env`) |

The reasoning behind each choice is in [docs/DECISIONS.md](docs/DECISIONS.md).

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest                 # offline, fake providers
uv run pytest -m integration  # needs the local DB
```

## Status

- Done: local demo (data pipeline, hybrid retrieval, agent, verification, MCP, API, UI), the full
  Labour Code indexed (1178 retrieval units), eval suite with results on the "Jak to działa" page.
- Next: security test suite in CI, public deployment.
