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

---

## D4. Structural chunking: one chunk per § / ust. (or per article without them)

**Context.** Citations must point to a concrete article / § / paragraph. The ELI HTML nests
`div.unit_<type>` elements (`arti` > `para`|`pass` > `pint` > `lett`) with stable ids, and the
`/struct` endpoint gives the same tree as JSON.

**Decision.** The parser walks the HTML tree of the "Tekst jednolity" section only. It stores
every article and every § / ust. as a `Provision` with its full path ("KP, Dział VII,
Rozdział I, art. 154 § 1"), act metadata and the consolidated text's ELI. Retrieval chunks are the
leaf units: a § / ust., or the whole article when it has none. Points (pkt) and letters (lit.) are
folded into their parent's text, because on their own they lack context ("20 dni - jeżeli...").
Repealed units are stored but never indexed. Ingestion cross-checks the parsed article ids
against `/struct`: 100% matched for all 7 acts.

**Alternatives.** Fixed-size token windows, kept only as the naive baseline for the ablation.
Point-level chunks: too short and context-free. The `/struct` JSON alone has no text.

**Consequences.** About 6.5k chunks, median about 200 characters, p95 below 1k. A few very long
units (e.g. definition lists in Ordynacja podatkowa, 15k characters) exceed the embedding context
and get truncated. That is acceptable for a demo; recorded as a known limitation.

---

## D5. Duplicate wordings: keep the later one

**Context.** Some consolidated texts contain two versions of the same unit. The first is marked
with a footnote "W tym brzmieniu obowiązuje do wejścia w życie zmiany...", and the next one is the
future wording. The same ids appear twice (e.g. KW art. 107, OP art. 75 § 2a).

**Decision.** Keep the last occurrence. Our consolidated texts are 1–3 years old, so by now the
future wording is almost always the one in force.

**Alternatives.** Parse the footnotes and model `valid_from` per unit. That is more correct but
costs time without visible demo value.

**Consequences.** The ids are unique and the database has a primary key on them. A handful of
units may show the wrong wording when an amendment has not yet entered into force.

---

## D6. Cross-references stored as relations, resolved within the corpus

**Context.** Provisions refer to each other ("art. 22 § 1", "§ 1 i 2", "art. 5 Kodeksu
cywilnego"). The agent's `follow_reference` tool and the provision preview need these links.

**Decision.** A regex extractor handles lists ("art. 132 i 133"), ranges ("art. 114-116"),
superscripts ("art. 22¹ § 3"), bare in-article units ("§ 1 i 2"), and the genitive names of the
indexed statutes. References to other acts ("...ustawy z dnia...") are dropped. A target unit
that does not exist falls back to its article. Result: about 3.4k resolved relations in the
`provision_refs` table.

**Alternatives.** An LLM-based extractor: higher recall on odd phrasings, but slow and costly on a
free tier, and non-deterministic.

**Consequences.** Some references are missed, e.g. when the act name follows a long point list.
The extractor is fast, deterministic and unit-tested.
