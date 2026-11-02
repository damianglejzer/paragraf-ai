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

---

## D7. Models and providers (all free tier), chosen by measurement

**Context.** Requirements: good Polish, structured output, fast enough for a live demo, free.
The Gemini free tier was probed on 2026-10-18 by calling each model until it returned 429:

| Model | Free-tier limit observed | Latency (thinking minimal) |
|---|---|---|
| gemini-3.5-flash | 5 RPM, **20 requests/day** | ~1 s |
| gemini-3.5-flash-lite | 15 RPM | ~10 s (overloaded) |
| gemini-2.5-flash-lite | 10 RPM | – |
| gemini-3.1-flash-lite | ≥16 RPM (no 429 in the probe) | ~1 s |
| gemma-4-26b-a4b-it | ≥16 RPM (no 429 in the probe), JSON schema supported | ~2.5 s |
| gemini-embedding-001 / -2 | **100 texts/min** (each batch item counts) | – |

**Decision.**
- Answers, query rewriting and eval-set generation use `gemini-3.1-flash-lite` with thinking
  set to "minimal".
- The citation judge uses `gemma-4-26b-a4b-it`. It is a different model family from the
  answering model, which reduces self-preference bias in LLM-as-judge.
- Embeddings use `jina-embeddings-v3` (multilingual, 768-dim Matryoshka, task-specific
  query/passage adapters). The reranker is `jina-reranker-v2-base-multilingual`. A new Jina key
  comes with a one-time pool of 10M free tokens, and both endpoints share it.
- Every vendor is configured in `.env` behind the `Embedder` / `Reranker` / `LLM` protocols, with
  `fake` implementations for offline CI.

**Alternatives.**
- Gemini embeddings: the quality is good, but at 100 texts/min indexing even the small corpus
  takes about 10 minutes, and the daily cap is unknown.
- Local models (bge-m3, multilingual-e5, mmlw): free and strong for Polish. However, query-time
  inference has to run on the 512 MB Render instance next to spaCy, which is too tight.
- jina-reranker-v3: same top results on probes, at about 3x the tokens per call.
- `gemini-3.5-flash` for answers: stronger reasoning, but 20 requests/day cannot serve a demo.

**Consequences.** Indexing the demo corpus takes about 30 s and about 150k Jina tokens. A query
costs about 3k reranker tokens, so the pool covers thousands of demo queries. When the pool or a
Gemini quota runs out, the provider raises `ProviderUnavailable`. The app then degrades: no
reranker, or full-text search only, or cached answers, plus a friendly "busy" message.

---

## D8. Lemmatizer: spaCy `pl_core_news_sm` (not simplemma)

**Context.** Postgres has no Polish text-search configuration, so lemmas are computed in Python and
indexed with `to_tsvector('simple', ...)`. The same lemmatizer must run at query time on a 512 MB
instance.

**Decision.** spaCy `pl_core_news_sm` with the parser and NER disabled.

**Alternatives.** Measured: simplemma reached 426 MB RSS and 3.3 s load time. spaCy reached 194 MB
and 0.5 s, with context-aware lemmas. Morfeusz2 has better dictionary coverage, but its packaging
for Python 3.12 is awkward.

**Consequences.** Some lemmas are imperfect (e.g. "kupiyć"). This is consistent between documents
and queries, so matching still works, and the vector channel compensates.

---

## D9. Small demo corpus

**Context.** Free-tier quotas (D7) and the demo's purpose: a recruiter should see a fast, working
system, not exhaustive coverage. The parser already handles whole statutes (8.5k provisions across
7 acts, verified against `/struct`).

**Decision.** Index only selected everyday topics (`backend/paragraf/corpus.py`):
- Kodeks pracy: employment relationship and termination, working time, leave, limitation;
- Ustawa o prawach konsumenta: information duties, 14-day withdrawal, non-conforming goods;
- Kodeks cywilny: limitation periods, lease.

That gives about 850 provisions and 644 retrieval chunks.

**Alternatives.** The full 7-act corpus (6.5k chunks). It would take hours of free-tier embedding
quota, and eval generation would exceed daily LLM limits.

**Consequences.** Indexing takes seconds and evals finish within the daily free quotas. Questions
outside these topics are refused, which is itself evaluated (out-of-scope category). Widening the
scope is a config change followed by re-running ingest and index.

---

## D10. LLM query rewriting before hybrid search

**Context.** Laypeople and statutes use different words ("sklep internetowy" vs "umowa zawarta na
odległość", "oddać" vs "odstąpić od umowy"). On the probe "Kupiłem buty w sklepie internetowym,
czy mogę je oddać?", the key provision (UPK art. 27) was not in the top 30 of any retriever.

**Decision.** A small LLM rewrites the question into statutory vocabulary. Both the original and the
rewritten query run through vector and full-text search, and all four rankings are fused with RRF.
The reranker then sees the original question together with its rewrite.

**Alternatives.** HyDE (generate a hypothetical provision): heavier, and it risks hallucinated
legal content in the query. A synonym dictionary: manual and brittle.

**Consequences.** The rewrite adds one call (~1 s, cached per question). In the probe, UPK art. 27
moved from outside the top 10 to rank 1. Its effect is measured as its own row in the ablation.
When the LLM is unavailable, search silently uses the original query only.

---

## D11. Judge model: Gemini Flash-Lite, not Gemma (revises D7)

**Context.** D7 used `gemma-4-26b-a4b-it` as the citation judge to avoid a model judging its own
family. In practice the free Gemma endpoint was unreliable. Some calls hung for minutes, which
stalled eval-set generation. Explanations degenerated ("wprost wprost ... gwarant```json"), and
JSON came wrapped in code fences.

**Decision.** The judge is `gemini-3.1-flash-lite` with thinking set to "low", under a separate
prompt that sees only the provision text and the claim, never the user question or the answer.
All Gemini calls get a 30 s HTTP timeout, and JSON output is extracted tolerantly.

**Alternatives.** `gemma-4-31b-it` returned 503 (overloaded). `gemini-3.5-flash` allows only 20
requests/day.

**Consequences.** The judge takes about 1–2 s and its explanations read naturally. Self-preference
bias is mitigated, not eliminated: the deterministic checks (existence, fuzzy quote match) do not
depend on any LLM, and a cross-family judge remains a configurable option (`JUDGE_MODEL`).

---

## D12. "Cost per query" reported as equivalent paid-tier cost

**Context.** The evaluation requires cost per query, but the demo runs on free tiers ($0).

**Decision.** Track tokens per stage and multiply by list prices (`providers/usage.py`). The UI
labels the result explicitly: "≈ $X w płatnym planie (demo: $0)".

**Consequences.** The number shows what the architecture would cost in production (about
$0.001 per question) without suggesting the demo incurs charges.

---

## D13. Handling false refusals: no cached refusals, ambiguity-aware planner, one retry

**Context.** In manual testing, "po jakim czasie pracy przysługuje mi dodatkowy urlop" was
rewritten by the planner as "nabycie prawa do *pierwszego* urlopu". Retrieval followed the wrong
lead (KP art. 153) and missed art. 154 § 1. The answering model then correctly refused ("no basis
in the provided provisions"). The refusal was cached, so every repeat replayed the error.

**Decision.**
1. Only full answers with citations are cached. Refusals and clarifying questions are not, and
   cached non-answers are ignored on read.
2. The planner prompt requires the rewrite to keep the question's meaning. When a term can mean
   different legal institutions, the planner asks a clarifying question that lists the options
   (with "dodatkowy urlop" as a worked example).
3. A `retry` node: when the answer is a refusal although retrieval returned provisions, search
   once more with the user's original wording (hybrid + rerank, no rewrite), merge the results
   and answer again. At most one retry per question. *(Removed later, see D15.)*

**Alternatives.** Dropping the rewrite altogether: D10 showed it is a large net win.
Always searching with both wordings: that already happens in "full" mode, yet a misleading
rewrite still dominates the fused ranking.

**Consequences.** A refusal now costs at most one extra retrieval and one extra answer call, and
only in the refusal case. A wrong refusal can no longer stick in the cache. The question that
triggered this now gets a clarifying question with both meanings. The false-refusal rate is
tracked in the generation eval (`false_refusal_rate`).

---

## D14. Lexical ranking: Postgres `ts_rank_cd`, not BM25

**Context.** The lexical half of hybrid retrieval was labelled "BM25" in the UI and in the eval
config, but the implementation is PostgreSQL full-text search: lemmas in a `tsvector('simple')`,
a GIN index, and `ts_rank_cd` for ranking (cover density, normalized by log of document length).

**Decision.** Name it accurately everywhere: "full-text (Postgres `ts_rank_cd`)".

**Alternatives.** True BM25 adds IDF (rare terms weigh more) and term-frequency saturation. It can
be computed in Python over the same lemmas (e.g. `bm25s`), or with a Postgres extension
(e.g. ParadeDB `pg_search`, availability on Neon to be checked). That is a candidate improvement,
to be justified by an ablation row "ts_rank_cd vs BM25".

**Consequences.** `ts_rank_cd` treats common words ("pracownik") like rare ones ("wypoczynkowy"),
which hurts long natural-language questions. RRF fusion with the vector ranking and the reranker
mitigate this.

---

## D15. Simpler agent graph: no retry node, no deadline tool

**Context.** The graph had grown a `retry` loop (D13, point 3) and a `deadline` action with a
`calculate_deadline` tool. Neither is central to the project's focus (retrieval quality and
citation verification), and both add branches to explain, test and keep stable in the demo.

**Decision.** Remove both. The graph is now linear after planning:
`plan → (respond_directly | gather → expand → answer → verify)`. A refusal from the answer node
ends the run.

**Alternatives.** Keeping the retry loop: it only helps when the planner's rewrite misleads
retrieval, which D13 points 1–2 and the "full" retrieval mode (original and rewritten queries
fused) already address.

**Consequences.** Every request costs at most 3 LLM calls, with no extra round on refusals. A
misleading rewrite can again produce a false refusal; `false_refusal_rate` in the generation eval
tracks this.

---

## D16. A small, free-tier eval suite

**Context.** The original plan (about 135 questions, five generation configs) meant well over a
thousand LLM calls, more than a free-tier daily quota, and a run took hours.

**Decision.** About 32 synthetic questions (16 regular, 5 multi-provision, 5 tricky, 6 out of
scope) and three generation configs: naive RAG, the full pipeline, and the full pipeline with
citation verification. The verified config reuses the full pipeline's runs and only drops wrong
citations. Retrieval is evaluated for all six modes, which costs one query rewrite per question.
One command (`paragraf.evaluation.run_all`) writes `evals/results/latest.json` for the UI.

**Alternatives.** A larger set run over several days: more precise numbers, but slow to iterate
on and impossible to re-run before a demo.

**Consequences.** The full suite is about 270 LLM calls including dataset generation, and runs in
under 20 minutes. With ~30 questions one question moves a percentage by about 3 points, so only
large differences between configs are meaningful; the UI shows whole percents for that reason.

---

## D17. LLM calls move from the Gemini free tier to the OpenAI API (revises D2, D7, D11)

**Context.** On 2026-11-02 the Gemini free tier answered in 2-13 s per call, and a client-side
limit of 14 RPM serialized the eval suite: a ~200-call run was heading for over an hour, and one
run had already stalled. The demo needs fast, predictable answers more than it needs a $0 bill.

**Decision.** All LLM calls go through the OpenAI API (`LLM_PROVIDER=openai`):
- `gpt-5.4-mini` with reasoning effort `none` for answers, the planner and query rewriting. This
  step decides quality (verbatim quotes, Polish legal language, valid JSON), and reasoning off
  keeps latency low.
- `gpt-5.4-nano` with reasoning effort `low` for the citation judge: a narrow classification
  task, so the cheapest model with a little reasoning is enough.

Structured output uses `response_format: json_schema` in non-strict mode, because the Pydantic
schemas use defaults and bounds that strict mode rejects; callers validate the JSON anyway.
Embeddings and the reranker stay on Jina (free token pool): changing embeddings would mean
re-indexing, and Jina was not the bottleneck. The Gemini provider remains available via `.env`.

**Alternatives.** Staying on Gemini with more parallelism: the per-minute limit caps it.
`gpt-5.4-mini` for the judge too: about 4x the price for a yes/no-style task.

**Consequences.** LLM calls are now billed: roughly $0.005 per chat question and a few cents per
eval run at list prices. The per-IP rate limit and daily request budget now protect real money,
not only quotas. The eval dataset generated earlier with Gemini is kept (`source:
"synthetic:gemini"`); all eval answers are regenerated with the new models.
