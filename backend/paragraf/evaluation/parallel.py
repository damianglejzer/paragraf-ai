"""Run eval questions a few at a time: API latency, not throughput limits, is the bottleneck."""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from paragraf.config import get_settings

WORKERS = 4
Connection = psycopg.Connection[dict[str, Any]]


@contextmanager
def thread_connections() -> Iterator[Callable[[], Connection]]:
    """Yield a getter for this thread's own connection; psycopg connections must not be shared
    between threads that run queries concurrently. All connections close on exit."""
    local = threading.local()
    opened: list[Connection] = []
    lock = threading.Lock()

    def get() -> Connection:
        conn: Connection | None = getattr(local, "conn", None)
        if conn is None:
            conn = psycopg.connect(
                get_settings().database_url, row_factory=dict_row, autocommit=True
            )
            local.conn = conn
            with lock:
                opened.append(conn)
        return conn

    try:
        yield get
    finally:
        for conn in opened:
            conn.close()


def parallel_map[T, R](fn: Callable[[T], R], items: list[T]) -> list[R]:
    """`fn` over `items` on WORKERS threads, results in input order."""
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(fn, items))
