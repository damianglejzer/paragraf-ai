"""Retrieval and generation metrics."""

import math
from collections.abc import Sequence


def article_of(provision_id: str) -> str:
    """'KP:art_154:par_1' -> 'KP:art_154'."""
    return ":".join(provision_id.split(":")[:2])


def is_relevant(retrieved_ids: Sequence[str], expected: str, level: str = "article") -> bool:
    """A hit is relevant if it covers the expected provision.

    level="unit": exact id match. level="article": same article (a § of the right article
    counts) — this is the granularity of a citation a reader checks.
    """
    if level == "unit":
        return expected in retrieved_ids
    target = article_of(expected)
    return any(article_of(r) == target for r in retrieved_ids)


def recall_at_k(
    ranked: Sequence[Sequence[str]], expected: Sequence[str], k: int, level: str = "article"
) -> float:
    """Fraction of expected provisions found in the top-k hits (each hit may cover several ids)."""
    if not expected:
        return math.nan
    top = [pid for hit in ranked[:k] for pid in hit]
    return sum(is_relevant(top, e, level) for e in expected) / len(expected)


def reciprocal_rank(
    ranked: Sequence[Sequence[str]], expected: Sequence[str], level: str = "article"
) -> float:
    if not expected:
        return math.nan
    for rank, hit in enumerate(ranked, start=1):
        if any(is_relevant(hit, e, level) for e in expected):
            return 1.0 / rank
    return 0.0


def mean(values: Sequence[float]) -> float:
    vals = [v for v in values if not math.isnan(v)]
    return sum(vals) / len(vals) if vals else math.nan


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(p / 100 * len(ordered)) - 1))
    return ordered[idx]
