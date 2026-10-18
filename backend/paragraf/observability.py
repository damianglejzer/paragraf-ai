"""Optional Langfuse tracing (enabled when LANGFUSE_* keys are set in .env).

Each chat request becomes one trace: an `agent` observation with the question and answer, one
child observation per agent step, and one `generation` per LLM / embedding / rerank call with
token usage and equivalent cost. Without keys every function here is a no-op.
"""

import logging
from functools import lru_cache
from typing import Any

from paragraf.config import get_settings
from paragraf.providers.usage import UsageLog

log = logging.getLogger("paragraf.observability")

STEP_TYPES = {
    "plan": "chain",
    "gather": "retriever",
    "expand": "tool",
    "answer": "chain",
    "verify": "evaluator",
}


@lru_cache(maxsize=1)
def _client() -> Any | None:
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
    except Exception as exc:  # observability must never break the app
        log.warning("Langfuse disabled: %s", exc)
        return None


def enabled() -> bool:
    return _client() is not None


def record_trace(
    question: str,
    result: dict[str, Any],
    steps: list[dict[str, Any]],
    usage: UsageLog,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Send one request as a Langfuse trace. Returns the trace id (or None if disabled)."""
    client = _client()
    if client is None:
        return None
    try:
        with client.start_as_current_observation(
            name="paragraf-chat",
            as_type="agent",
            input={"question": question},
            output=result,
            metadata=metadata or {},
        ) as root:
            for step in steps:
                obs = client.start_observation(
                    name=step["node"],
                    as_type=STEP_TYPES.get(step["node"], "span"),
                    input={"title": step["title"]},
                    output=step.get("detail"),
                    metadata={"ms": step.get("ms")},
                )
                obs.end()
            for rec in usage.records:
                gen = client.start_observation(
                    name=f"{rec.stage}:{rec.model}",
                    as_type="embedding" if "embedding" in rec.model else "generation",
                    model=rec.model,
                    usage_details={"input": rec.input_tokens, "output": rec.output_tokens},
                    cost_details={"total": rec.cost_usd},
                    metadata={"cached": rec.cached, "stage": rec.stage},
                )
                gen.end()
            trace_id: str | None = root.trace_id
        client.flush()
        return trace_id
    except Exception as exc:
        log.warning("Langfuse trace failed: %s", exc)
        return None
