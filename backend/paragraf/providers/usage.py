"""Per-request usage tracking (tokens, cost) shared by all providers via a context variable.

We run on free tiers and pay $0; `cost_usd` is the *equivalent paid-tier cost*, reported so the
demo can show what the system would cost at list prices (docs/DECISIONS.md, D11).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from pydantic import BaseModel

# USD per 1M tokens (input, output), list prices checked 2026-10-18
PRICES: dict[str, tuple[float, float]] = {
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash": (0.30, 2.50),
    "gemma-4-26b-a4b-it": (0.0, 0.0),  # offered free-only through the Gemini API
    "jina-embeddings-v3": (0.05, 0.0),
    "jina-reranker-v2-base-multilingual": (0.05, 0.0),
    "jina-reranker-v3": (0.05, 0.0),
}


class UsageRecord(BaseModel):
    stage: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False

    @property
    def cost_usd(self) -> float:
        if self.cached:
            return 0.0
        price_in, price_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000


class UsageLog(BaseModel):
    records: list[UsageRecord] = []

    @property
    def cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.records)

    @property
    def total_tokens(self) -> int:
        return sum(r.input_tokens + r.output_tokens for r in self.records)

    def by_stage(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for r in self.records:
            s = out.setdefault(r.stage, {"tokens": 0, "cost_usd": 0.0})
            s["tokens"] += r.input_tokens + r.output_tokens
            s["cost_usd"] += r.cost_usd
        return out


_current: ContextVar[UsageLog | None] = ContextVar("usage_log", default=None)
_stage: ContextVar[str] = ContextVar("usage_stage", default="other")


@contextmanager
def track() -> Iterator[UsageLog]:
    log = UsageLog()
    token = _current.set(log)
    try:
        yield log
    finally:
        _current.reset(token)


@contextmanager
def stage(name: str) -> Iterator[None]:
    token = _stage.set(name)
    try:
        yield
    finally:
        _stage.reset(token)


def record(model: str, input_tokens: int, output_tokens: int = 0, cached: bool = False) -> None:
    log = _current.get()
    if log is not None:
        log.records.append(
            UsageRecord(
                stage=_stage.get(),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached=cached,
            )
        )
