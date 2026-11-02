"""Demo protection: client IP detection, rate limits, request guards and quotas."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from paragraf.api import protection
from paragraf.api.main import MAX_BODY_BYTES, app


@pytest.mark.parametrize(
    ("forwarded", "hops", "expected"),
    [
        ("6.6.6.6", 0, "10.0.0.1"),  # no trusted proxy: the header is ignored
        ("6.6.6.6, 1.2.3.4", 1, "1.2.3.4"),  # spoofed left part is skipped
        ("1.2.3.4", 1, "1.2.3.4"),
        ("6.6.6.6, 1.2.3.4, 10.1.1.1", 2, "1.2.3.4"),
        ("1.2.3.4", 2, "10.0.0.1"),  # fewer entries than proxies: fall back to the peer
        (None, 1, "10.0.0.1"),
    ],
)
def test_client_ip_trusts_only_proxy_written_hops(
    forwarded: str | None, hops: int, expected: str
) -> None:
    assert protection.client_ip(forwarded, "10.0.0.1", hops) == expected


def test_rate_limiter_is_per_client() -> None:
    limiter = protection.RateLimiter(per_minute=2)
    assert [limiter.check("a") == 0 for _ in range(3)] == [True, True, False]
    assert limiter.check("b") == 0


def test_ip_hash_hides_the_ip_and_changes_daily() -> None:
    day = dt.date(2026, 11, 2)
    digest = protection.ip_hash("1.2.3.4", day)
    assert "1.2.3.4" not in digest
    assert digest != protection.ip_hash("1.2.3.4", day + dt.timedelta(days=1))
    assert digest == protection.ip_hash("1.2.3.4", day)


# The guards below reject requests before any handler (and so before the DB) is reached.
client = TestClient(app)


def test_oversized_body_is_rejected_with_security_headers() -> None:
    resp = client.post(
        "/api/chat",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"


def test_overlong_question_fails_validation() -> None:
    assert client.post("/api/chat", json={"question": "x" * 2001}).status_code == 422


def test_too_much_history_fails_validation() -> None:
    history = [{"role": "user", "content": "a"}] * 9
    assert client.post("/api/chat", json={"question": "a", "history": history}).status_code == 422


def test_api_docs_are_off_by_default() -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


@pytest.mark.integration
def test_quotas_stop_at_the_limit_atomically() -> None:
    from paragraf.config import get_settings
    from paragraf.db import repository as repo

    with repo.connect() as conn:
        repo.init_schema(conn, get_settings().embedding_dim)
        conn.execute("DELETE FROM ip_usage_daily")
        conn.commit()
        assert [protection.try_consume_ip_quota(conn, "9.9.9.9", 2) for _ in range(3)] == [
            True,
            True,
            False,
        ]
        assert protection.try_consume_ip_quota(conn, "8.8.8.8", 2)
        assert not protection.try_consume_budget(conn, 0)
        stored = conn.execute("SELECT ip_hash FROM ip_usage_daily").fetchall()
        assert all("9.9.9.9" not in r["ip_hash"] for r in stored)
        conn.execute("DELETE FROM ip_usage_daily")
