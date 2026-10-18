"""Build search indexes: lemmas (full-text), embeddings (pgvector) and the naive baseline.

Usage: uv run python -m paragraf.indexing.index [--skip-naive]
Idempotent: embeddings are cached on disk, so re-running costs no API quota.
"""

import argparse
import logging
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from paragraf.config import get_settings
from paragraf.db import repository as repo
from paragraf.db.schema import VECTOR_INDEXES_SQL
from paragraf.indexing.lemmatize import lemmatize_many
from paragraf.providers.base import Embedder
from paragraf.providers.factory import make_embedder

log = logging.getLogger("paragraf.index")

MAX_EMBED_CHARS = 6000
NAIVE_CHUNK_CHARS = 1000
NAIVE_OVERLAP = 200


def embedding_text(row: dict[str, Any], act_name: str) -> str:
    """Contextual header + text. The header gives short units (e.g. '§ 2') their topic."""
    titles = " > ".join(t for t in row["hierarchy_titles"] if t)
    header = f"{act_name}" + (f" — {titles}" if titles else "")
    return f"{header}\n{row['citation']}\n{row['text']}"[:MAX_EMBED_CHARS]


def naive_chunks(rows: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    """Fixed-size character windows over the act's raw text, ignoring structure.

    Returns (chunk text, ids of provisions overlapping the window) for recall evaluation.
    """
    spans: list[tuple[int, int, str]] = []
    parts: list[str] = []
    pos = 0
    for row in rows:
        text = row["text"] + "\n"
        spans.append((pos, pos + len(text), row["id"]))
        parts.append(text)
        pos += len(text)
    full = "".join(parts)
    out: list[tuple[str, list[str]]] = []
    step = NAIVE_CHUNK_CHARS - NAIVE_OVERLAP
    for start in range(0, max(len(full) - NAIVE_OVERLAP, 1), step):
        end = start + NAIVE_CHUNK_CHARS
        ids = [pid for s, e, pid in spans if s < end and e > start]
        out.append((full[start:end], ids))
    return out


def _embed_in_batches(embedder: Embedder, texts: list[str], batch: int = 500) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch):
        vectors.extend(embedder.embed(texts[i : i + batch], "document"))
        log.info("embedded %d/%d", min(i + batch, len(texts)), len(texts))
    return vectors


def index_provisions(conn: psycopg.Connection[Any], embedder: Embedder) -> None:
    acts = {r["code"]: r["name"] for r in conn.execute("SELECT code, name FROM acts")}
    rows = conn.execute(
        "SELECT id, act_code, citation, hierarchy_titles, text FROM provisions "
        "WHERE is_chunk AND NOT repealed ORDER BY act_code, ord"
    ).fetchall()
    log.info("lemmatizing %d chunks", len(rows))
    texts = [embedding_text(r, acts[r["act_code"]]) for r in rows]
    lemmas = lemmatize_many(texts)
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE provisions SET lemmas = %s WHERE id = %s",
            [(" ".join(lem), r["id"]) for lem, r in zip(lemmas, rows, strict=True)],
        )
    vectors = _embed_in_batches(embedder, texts)
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE provisions SET embedding = %s WHERE id = %s",
            [(v, r["id"]) for v, r in zip(vectors, rows, strict=True)],
        )
    conn.commit()


def index_naive(conn: psycopg.Connection[Any], embedder: Embedder) -> None:
    conn.execute("DELETE FROM naive_chunks")
    codes = [r["code"] for r in conn.execute("SELECT code FROM acts ORDER BY code").fetchall()]
    for code in codes:
        rows = conn.execute(
            "SELECT id, text FROM provisions WHERE act_code = %s AND is_chunk AND NOT repealed "
            "ORDER BY ord",
            (code,),
        ).fetchall()
        chunks = naive_chunks(rows)
        vectors = _embed_in_batches(embedder, [c for c, _ in chunks])
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO naive_chunks (act_code, text, provision_ids, embedding) "
                "VALUES (%s, %s, %s, %s)",
                [(code, c, ids, v) for (c, ids), v in zip(chunks, vectors, strict=True)],
            )
        log.info("%s: %d naive chunks", code, len(chunks))
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-naive", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    embedder = make_embedder(settings)
    log.info("embedder: %s (dim=%d)", embedder.name, embedder.dim)
    with repo.connect() as conn:
        repo.init_schema(conn, settings.embedding_dim)
        register_vector(conn)
        index_provisions(conn, embedder)
        if not args.skip_naive:
            index_naive(conn, embedder)
        conn.execute(VECTOR_INDEXES_SQL.encode())
    log.info("done")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    main()
