"""Thin data-access layer over psycopg 3."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from paragraf.config import get_settings
from paragraf.db.schema import schema_sql
from paragraf.parsing.models import ActMeta, CrossReference, Provision

PROVISION_COLUMNS = (
    "id, act_code, level, article, unit, parent_id, hierarchy, hierarchy_titles, "
    "citation, full_path, text, repealed, is_chunk, ord"
)


@contextmanager
def connect(url: str | None = None) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    conn = psycopg.connect(url or get_settings().database_url, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema(conn: psycopg.Connection[Any], embedding_dim: int) -> None:
    conn.execute(schema_sql(embedding_dim).encode())
    from pgvector.psycopg import register_vector

    register_vector(conn)


def upsert_act(conn: psycopg.Connection[Any], act: ActMeta) -> None:
    conn.execute(
        """INSERT INTO acts (code, name, eli, title, announcement_date)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, eli = EXCLUDED.eli,
             title = EXCLUDED.title, announcement_date = EXCLUDED.announcement_date""",
        (act.code, act.name, act.eli, act.title, act.announcement_date),
    )


def replace_provisions(
    conn: psycopg.Connection[Any],
    act_code: str,
    provisions: Iterable[Provision],
) -> int:
    conn.execute("DELETE FROM provisions WHERE act_code = %s", (act_code,))
    rows = [
        (
            p.id,
            p.act_code,
            p.level,
            p.article,
            p.unit,
            p.parent_id,
            p.hierarchy,
            p.hierarchy_titles,
            p.citation,
            p.full_path,
            p.text,
            p.repealed,
            p.is_chunk,
            p.order,
        )
        for p in provisions
    ]
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO provisions ({PROVISION_COLUMNS}) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    return len(rows)


def replace_references(conn: psycopg.Connection[Any], refs: Iterable[CrossReference]) -> int:
    rows = [(r.source_id, r.target_id, r.raw) for r in refs]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO provision_refs (source_id, target_id, raw) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            rows,
        )
    return len(rows)


def get_provision(conn: psycopg.Connection[Any], provision_id: str) -> dict[str, Any] | None:
    """Fetch a provision; an unknown unit id ('KP:art_5:par_9') falls back to its article."""
    row = conn.execute(
        f"SELECT {PROVISION_COLUMNS} FROM provisions WHERE id = %s", (provision_id,)
    ).fetchone()
    if row is None and provision_id.count(":") == 2:
        row = conn.execute(
            f"SELECT {PROVISION_COLUMNS} FROM provisions WHERE id = %s",
            (provision_id.rsplit(":", 1)[0],),
        ).fetchone()
    return row


def get_children(conn: psycopg.Connection[Any], article_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        f"SELECT {PROVISION_COLUMNS} FROM provisions WHERE parent_id = %s ORDER BY ord",
        (article_id,),
    ).fetchall()


def get_outgoing_references(conn: psycopg.Connection[Any], provision_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT target_id FROM provision_refs WHERE source_id = %s OR source_id IN "
        "(SELECT id FROM provisions WHERE parent_id = %s) ORDER BY target_id",
        (provision_id, provision_id),
    ).fetchall()
    return [r["target_id"] for r in rows]
