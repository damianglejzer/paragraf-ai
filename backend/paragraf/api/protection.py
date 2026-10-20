"""Demo cost protection: per-IP rate limit, daily budget with a hard switch, answer cache."""

import datetime as dt
import json
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

import psycopg


class RateLimiter:
    """In-memory sliding window per client IP (single instance deployment)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """0 if allowed (and recorded), otherwise seconds until the next slot."""
        now = time.monotonic()
        with self._lock:
            window = self._hits[key]
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= self.per_minute:
                return 60 - (now - window[0])
            window.append(now)
            return 0.0


def question_key(question: str) -> str:
    """Normalize so trivial variations ("Ile dni urlopu?" / "ile dni urlopu") share a cache key."""
    text = re.sub(r"[^\w\s]", " ", question.lower())
    return " ".join(text.split())


def is_cacheable(payload: dict[str, Any]) -> bool:
    """Only full answers are cached. A refusal or clarifying question may stem from a planner
    or retrieval miss; caching it would replay the same mistake on every repeat of the question.
    """
    return payload.get("status") == "answer" and bool(payload.get("citations"))


def get_cached(conn: psycopg.Connection[Any], question: str) -> dict[str, Any] | None:
    row = conn.execute(
        "UPDATE answer_cache SET hits = hits + 1 "
        "WHERE question_key = %s AND payload->>'status' = 'answer' RETURNING payload",
        (question_key(question),),
    ).fetchone()
    conn.commit()
    return dict(row["payload"]) if row else None


def put_cached(conn: psycopg.Connection[Any], question: str, payload: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO answer_cache (question_key, question, payload) VALUES (%s, %s, %s)
           ON CONFLICT (question_key) DO UPDATE SET payload = EXCLUDED.payload,
             created_at = now()""",
        (question_key(question), question, json.dumps(payload, ensure_ascii=False, default=str)),
    )
    conn.commit()


def budget_exhausted(conn: psycopg.Connection[Any], limit: int) -> bool:
    row = conn.execute(
        "SELECT requests FROM usage_daily WHERE day = %s", (dt.datetime.now(dt.UTC).date(),)
    ).fetchone()
    return row is not None and int(row["requests"]) >= limit


def record_usage(conn: psycopg.Connection[Any], tokens: int, cost_usd: float) -> None:
    conn.execute(
        """INSERT INTO usage_daily (day, requests, tokens, cost_usd) VALUES (%s, 1, %s, %s)
           ON CONFLICT (day) DO UPDATE SET requests = usage_daily.requests + 1,
             tokens = usage_daily.tokens + EXCLUDED.tokens,
             cost_usd = usage_daily.cost_usd + EXCLUDED.cost_usd""",
        (dt.datetime.now(dt.UTC).date(), tokens, cost_usd),
    )
    conn.commit()


def usage_today(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    row = conn.execute(
        "SELECT requests, tokens, cost_usd FROM usage_daily WHERE day = %s",
        (dt.datetime.now(dt.UTC).date(),),
    ).fetchone()
    return dict(row) if row else {"requests": 0, "tokens": 0, "cost_usd": 0.0}
