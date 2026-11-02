"""Tiny persistent key-value cache (SQLite) for embeddings and LLM calls.

API calls cost time and money: re-running indexing or evals must not re-pay for
identical requests.
"""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        self._lock = threading.Lock()

    @staticmethod
    def key(*parts: Any) -> str:
        raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        with self._lock:
            row = self._conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        with self._lock:
            for i in range(0, len(keys), 500):
                chunk = keys[i : i + 500]
                marks = ",".join("?" * len(chunk))
                for k, v in self._conn.execute(f"SELECT k, v FROM kv WHERE k IN ({marks})", chunk):
                    out[k] = json.loads(v)
        return out

    def set(self, key: str, value: Any) -> None:
        self.set_many({key: value})

    def set_many(self, items: dict[str, Any]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)",
                [(k, json.dumps(v, ensure_ascii=False)) for k, v in items.items()],
            )
            self._conn.commit()
