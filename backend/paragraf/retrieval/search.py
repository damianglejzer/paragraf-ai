"""Retrieval: full-text over lemmas, vector search, RRF fusion, reranking, naive baseline.

All pipelines return `Hit`s whose `ids` are provision ids, so metrics are comparable.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import psycopg
from pgvector.psycopg import register_vector

from paragraf.indexing.lemmatize import lemmatize
from paragraf.providers.base import Embedder, Reranker

Mode = Literal["naive", "vector", "fulltext", "hybrid", "hybrid_rerank", "full"]
# full = query rewrite + hybrid (original and rewritten queries) + rerank
RRF_K = 60


@dataclass
class Hit:
    id: str  # provision id (for naive chunks: the first overlapping provision)
    score: float
    text: str
    citation: str = ""
    full_path: str = ""
    ids: list[str] = field(default_factory=list)  # all provision ids covered by this hit
    sources: dict[str, int] = field(default_factory=dict)  # retriever name -> rank (1-based)


_SELECT = "SELECT id, citation, full_path, text"


def _hit(row: dict[str, Any], score: float, source: str, rank: int) -> Hit:
    return Hit(
        id=row["id"],
        score=score,
        text=row["text"],
        citation=row["citation"],
        full_path=row["full_path"],
        ids=[row["id"]],
        sources={source: rank},
    )


def build_tsquery(query: str) -> str | None:
    """OR of the query's lemmas. AND is too strict for natural-language questions."""
    lemmas = list(dict.fromkeys(lemmatize(query)))
    safe = [lemma.replace("'", "") for lemma in lemmas if lemma.replace("'", "")]
    return " | ".join(f"'{lemma}'" for lemma in safe) or None


def fulltext_search(
    conn: psycopg.Connection[Any], query: str, k: int, act: str | None = None
) -> list[Hit]:
    tsquery = build_tsquery(query)
    if tsquery is None:
        return []
    rows = conn.execute(
        f"""{_SELECT}, ts_rank_cd(tsv, q, 1) AS score
            FROM provisions, to_tsquery('simple', %s) q
            WHERE is_chunk AND NOT repealed AND tsv @@ q
              AND (%s::text IS NULL OR act_code = %s)
            ORDER BY score DESC LIMIT %s""",
        (tsquery, act, act, k),
    ).fetchall()
    return [_hit(r, float(r["score"]), "fulltext", i + 1) for i, r in enumerate(rows)]


def vector_search(
    conn: psycopg.Connection[Any],
    query_vec: list[float],
    k: int,
    act: str | None = None,
) -> list[Hit]:
    register_vector(conn)
    import numpy as np

    rows = conn.execute(
        f"""{_SELECT}, 1 - (embedding <=> %s) AS score
            FROM provisions
            WHERE is_chunk AND NOT repealed AND embedding IS NOT NULL
              AND (%s::text IS NULL OR act_code = %s)
            ORDER BY embedding <=> %s LIMIT %s""",
        (np.array(query_vec), act, act, np.array(query_vec), k),
    ).fetchall()
    return [_hit(r, float(r["score"]), "vector", i + 1) for i, r in enumerate(rows)]


def naive_search(conn: psycopg.Connection[Any], query_vec: list[float], k: int) -> list[Hit]:
    register_vector(conn)
    import numpy as np

    rows = conn.execute(
        """SELECT id, text, provision_ids, 1 - (embedding <=> %s) AS score
           FROM naive_chunks ORDER BY embedding <=> %s LIMIT %s""",
        (np.array(query_vec), np.array(query_vec), k),
    ).fetchall()
    return [
        Hit(
            id=r["provision_ids"][0] if r["provision_ids"] else f"naive:{r['id']}",
            score=float(r["score"]),
            text=r["text"],
            ids=list(r["provision_ids"]),
            sources={"naive": i + 1},
        )
        for i, r in enumerate(rows)
    ]


def rrf_fuse(*rankings: list[Hit], k: int = RRF_K) -> list[Hit]:
    """Reciprocal Rank Fusion: score = sum over rankings of 1 / (k + rank)."""
    fused: dict[str, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            entry = fused.get(hit.id)
            if entry is None:
                entry = Hit(**{**hit.__dict__, "score": 0.0, "sources": {}})
                fused[hit.id] = entry
            entry.score += 1.0 / (k + rank)
            entry.sources.update(hit.sources)
    return sorted(fused.values(), key=lambda h: -h.score)


def rerank_hits(query: str, hits: list[Hit], reranker: Reranker, top_n: int) -> list[Hit]:
    if not hits:
        return []
    docs = [f"{h.citation}\n{h.text}" for h in hits]
    ranked = reranker.rerank(query, docs, top_n)
    out = []
    for rank, (idx, score) in enumerate(ranked, start=1):
        hit = hits[idx]
        out.append(
            Hit(**{**hit.__dict__, "score": score, "sources": {**hit.sources, "rerank": rank}})
        )
    return out


@dataclass
class Retriever:
    conn: psycopg.Connection[Any]
    embedder: Embedder
    reranker: Reranker | None = None
    rewriter: Callable[[str], str | None] | None = None
    candidates: int = 40  # per retriever, before fusion
    rerank_pool: int = 25  # fused candidates sent to the reranker
    last_rewrite: str | None = None

    def search(
        self,
        query: str,
        k: int = 8,
        mode: Mode = "full",
        act: str | None = None,
        rewrite: str | None = None,
    ) -> list[Hit]:
        """`rewrite`: an already rewritten query (e.g. from the agent planner) - skips the
        rewriter call in "full" mode."""
        self.last_rewrite = None
        if mode == "fulltext":
            return fulltext_search(self.conn, query, k, act)
        if mode == "naive":
            return naive_search(self.conn, self.embedder.embed([query], "query")[0], k)
        if mode == "vector":
            return vector_search(self.conn, self.embedder.embed([query], "query")[0], k, act)

        queries = [query]
        if mode == "full" and (rewrite or self.rewriter is not None):
            rewritten = rewrite or (self.rewriter(query) if self.rewriter else None)
            if rewritten and rewritten != query:
                self.last_rewrite = rewritten
                queries.append(rewritten)
        vectors = self.embedder.embed(queries, "query")
        rankings: list[list[Hit]] = []
        for q, vec in zip(queries, vectors, strict=True):
            rankings.append(vector_search(self.conn, vec, self.candidates, act))
            rankings.append(fulltext_search(self.conn, q, self.candidates, act))
        fused = rrf_fuse(*rankings)
        if mode == "hybrid" or self.reranker is None:
            return fused[:k]
        rerank_query = f"{query}\n{self.last_rewrite}" if self.last_rewrite else query
        return rerank_hits(rerank_query, fused[: self.rerank_pool], self.reranker, k)
