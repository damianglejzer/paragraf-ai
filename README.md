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
- **Demo protection.** Per-IP rate limit, a daily request budget with a cache-only fallback, an
  answer cache and a query length limit.

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
uv run uvicorn paragraf.api.main:app --port 8010
cd frontend && npm install && npm run dev
```

### Evaluation

```bash
uv run python -m paragraf.evaluation.generate   # ~32 synthetic questions, ~70 LLM calls
uv run python -m paragraf.evaluation.run_all    # retrieval + generation, writes evals/results/latest.json
```

The suite is deliberately small: `run_all` makes roughly 200 LLM calls (a few cents with the
mini/nano models) and runs 4 questions in parallel. LLM responses are cached on disk, so a re-run only pays for unfinished calls. The
results appear on the "Jak to działa" page.

### MCP server

```bash
uv run python -m paragraf.mcp_server.server          # stdio (Claude Desktop / Claude Code)
uv run python -m paragraf.mcp_server.server --http   # streamable HTTP on :8765
```

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
