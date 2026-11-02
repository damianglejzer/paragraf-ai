# Paragraf AI

AI assistant for Polish labour law (the full Kodeks pracy, plus a few topics from KC and the
consumer rights act). An agent answers questions about statutes and always cites a
concrete article / § / paragraph (ust.). A separate step automatically verifies that each cited
provision exists and actually supports the claim. The main differentiator is rigorous evaluation
and citation verification, not the chat itself.

Portfolio project for junior AI/ML Engineer roles. Priorities: low running cost (cheap OpenAI
mini/nano models for the LLM, free tiers elsewhere), the demo is smooth, fast and polished. Legal accuracy matters, but it is secondary to a working,
impressive demo. Data comes from the official Sejm ELI API (https://api.sejm.gov.pl/eli), using
the newest consolidated text (tekst jednolity) that has an HTML version. No PDF parsing.

## Layout
- `backend/paragraf/` - Python package (eli client, parsing, db, indexing, retrieval,
  generation, agent, mcp_server, api, providers)
- `backend/tests/` - pytest
- `evals/` - dataset, eval scripts, results (JSON consumed by the frontend)
- `frontend/` - React + TypeScript + Vite
- `docs/DECISIONS.md` - design decisions (context → decision → alternatives → consequences)
- `docs/eli_openapi.yaml` - the ELI API spec the client is written against

## Conventions
- Code, comments, commits and README in English. Talk to the user in Polish.
- Python 3.12, `uv`, type hints everywhere, `ruff` (lint + format), `mypy --strict`.
- Tests for every piece of parsing and retrieval logic.
- Small, descriptive commits after each working step.
- Record significant decisions in `docs/DECISIONS.md`.
- Secrets only in `.env` (see `.env.example`). Nothing secret in the repo.
- LLM, embeddings and reranker sit behind provider interfaces chosen via `.env`. A `fake`
  provider keeps tests and CI offline.

## Commands
- `docker compose up -d db` - Postgres 16 + pgvector on port 5434
- `uv sync` - install deps
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy`
- `uv run pytest` (add `-m integration` for DB/network tests)
