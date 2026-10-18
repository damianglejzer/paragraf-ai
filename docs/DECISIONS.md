# Design decisions

Format: **Context → Decision → Alternatives → Consequences**.

---

## D1. Text source: newest consolidated text with HTML, no PDF parsing

**Context.** A consolidated text (tekst jednolity, t.j.) is published as a separate act of type
*Obwieszczenie* ("…w sprawie ogłoszenia jednolitego tekstu ustawy X"). The base act points to it
through the reference key "Inf. o tekście jednolitym". When this project started (Oct 2026),
the newest consolidated texts (2025–2026) were available only as PDF: `textHTML=false` and
`/struct` returned 404. Older consolidated texts have HTML and a structure endpoint.

**Decision.** For each statute, a discovery script searches the API and picks the newest
consolidated text that has `textHTML=true`. Act IDs are discovered at runtime, never hard-coded.

**Alternatives.**
- Newest consolidated text from PDF (pymupdf): the most up to date, but layout-based parsing
  (headers, footnotes, two-column amendment notes) costs a lot of time for little demo value.
- ISAP "tekst ujednolicony" (type `U` PDF): fresher still, but unofficial and also PDF-only.

**Consequences.** Some provisions may be 1–3 years out of date. The UI shows the source text and
its date for every citation, and the disclaimer says this is not legal advice. Clean HTML gives a
reliable art/§/ust. structure, which the citation verification depends on.

---

## D2. Everything runs on free tiers

**Context.** This is a public portfolio demo with no revenue. Any paid dependency is a risk.

**Decision.** Gemini API free tier for the LLM and embeddings, a free-tier reranker API, Neon for
Postgres, Render for the backend, Vercel for the frontend, Langfuse Cloud Hobby. Details are in
the per-component decisions below.

**Alternatives.** Paid APIs (OpenAI, Anthropic, Cohere production keys) would give higher rate
limits and a choice of models, but they cost money and need a card on file.

**Consequences.** Free-tier rate limits shape the design: responses for the example questions are
cached, there is a daily budget with a cache-only fallback, eval runs cache LLM calls on disk, and
when a limit is hit the UI shows a friendly "busy" state instead of an error.

---

## D3. Local Postgres via Docker Compose on port 5434

**Context.** Ports 5432 and 5433 are taken on the dev machine (system Postgres, another project).

**Decision.** `pgvector/pgvector:pg16` image, published on host port 5434.

**Alternatives.** A separate vector DB (Qdrant, Chroma). Rejected: one Postgres holds relational
data, full-text search and vectors, and Neon offers pgvector for free.

**Consequences.** Hybrid retrieval can be a single SQL round trip. Production uses the same engine.
