"""Demo cost protection: per-IP limits, a global daily budget, a concurrency cap, answer cache."""

import datetime as dt
import hashlib
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


def _today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def try_consume_budget(conn: psycopg.Connection[Any], limit: int) -> bool:
    """Reserve one request from today's global budget; False when it is used up.

    Check and increment are one statement, so concurrent requests cannot overshoot the limit.
    """
    row = conn.execute(
        """INSERT INTO usage_daily (day, requests) VALUES (%s, 1)
           ON CONFLICT (day) DO UPDATE SET requests = usage_daily.requests + 1
             WHERE usage_daily.requests < %s
           RETURNING requests""",
        (_today(), limit),
    ).fetchone()
    conn.commit()
    return row is not None and limit > 0


def ip_hash(ip: str, day: dt.date) -> str:
    """Daily-salted hash: enough to count requests per client, without storing the IP."""
    return hashlib.sha256(f"{day.isoformat()}|{ip}".encode()).hexdigest()[:32]


def try_consume_ip_quota(conn: psycopg.Connection[Any], ip: str, limit: int) -> bool:
    """Reserve one of today's requests for this client IP; False when it is used up."""
    day = _today()
    conn.execute("DELETE FROM ip_usage_daily WHERE day < %s", (day - dt.timedelta(days=1),))
    row = conn.execute(
        """INSERT INTO ip_usage_daily (day, ip_hash, requests) VALUES (%s, %s, 1)
           ON CONFLICT (day, ip_hash) DO UPDATE SET requests = ip_usage_daily.requests + 1
             WHERE ip_usage_daily.requests < %s
           RETURNING requests""",
        (day, ip_hash(ip, day), limit),
    ).fetchone()
    conn.commit()
    return row is not None and limit > 0


def record_usage(conn: psycopg.Connection[Any], tokens: int, cost_usd: float) -> None:
    """Add a finished request's tokens and cost (the request itself was counted up front)."""
    conn.execute(
        """INSERT INTO usage_daily (day, requests, tokens, cost_usd) VALUES (%s, 0, %s, %s)
           ON CONFLICT (day) DO UPDATE SET tokens = usage_daily.tokens + EXCLUDED.tokens,
             cost_usd = usage_daily.cost_usd + EXCLUDED.cost_usd""",
        (_today(), tokens, cost_usd),
    )
    conn.commit()


def client_ip(forwarded_for: str | None, peer: str | None, trusted_hops: int) -> str:
    """The client's IP. X-Forwarded-For is trusted only as far as our own proxies wrote it:
    each trusted proxy appends the address it saw, so the client is `trusted_hops` entries from
    the right. Anything to the left of that was sent by the client and can be forged."""
    if trusted_hops > 0 and forwarded_for:
        hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
        if len(hops) >= trusted_hops:
            return hops[-trusted_hops]
    return peer or "unknown"
