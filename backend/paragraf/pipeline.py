"""End-to-end RAG pipeline: retrieve -> generate answer with citations -> verify citations.

Used by the evaluation scripts directly and by the agent as its core answering step.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from paragraf.generation.answer import Answer, generate_answer
from paragraf.generation.verify import CitationCheck, ProvisionLookup, verify_citations
from paragraf.providers import usage as usage_tracking
from paragraf.providers.base import LLM
from paragraf.providers.usage import UsageLog
from paragraf.retrieval.search import Hit, Mode, Retriever


@dataclass
class PipelineConfig:
    mode: Mode = "full"
    k: int = 8
    verify: bool = True
    # with verification on, citations judged "wrong" are removed from the answer shown
    drop_wrong_citations: bool = True


@dataclass
class PipelineResult:
    question: str
    answer: Answer
    hits: list[Hit]
    checks: list[CitationCheck] = field(default_factory=list)
    rewrite: str | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    usage: UsageLog = field(default_factory=UsageLog)

    @property
    def total_ms(self) -> float:
        return sum(self.timings_ms.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "rewrite": self.rewrite,
            "answer": self.answer.model_dump(),
            "checks": [c.model_dump() for c in self.checks],
            "hits": [
                {"id": h.id, "citation": h.citation, "score": h.score, "sources": h.sources}
                for h in self.hits
            ],
            "timings_ms": {k: round(v, 1) for k, v in self.timings_ms.items()},
            "total_ms": round(self.total_ms, 1),
            "tokens": self.usage.total_tokens,
            "cost_usd": self.usage.cost_usd,
        }


def run_pipeline(
    question: str,
    retriever: Retriever,
    llm: LLM,
    judge: LLM | None,
    lookup: ProvisionLookup,
    config: PipelineConfig | None = None,
) -> PipelineResult:
    cfg = config or PipelineConfig()
    timings: dict[str, float] = {}
    with usage_tracking.track() as log:
        start = time.perf_counter()
        with usage_tracking.stage("retrieval"):
            hits = retriever.search(question, k=cfg.k, mode=cfg.mode)
        timings["retrieval"] = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        with usage_tracking.stage("generation"):
            answer, _ = generate_answer(llm, question, hits)
        timings["generation"] = (time.perf_counter() - start) * 1000

        checks: list[CitationCheck] = []
        if cfg.verify and answer.citations:
            start = time.perf_counter()
            with usage_tracking.stage("verification"):
                checks, _ = verify_citations(answer.citations, lookup, judge)
            timings["verification"] = (time.perf_counter() - start) * 1000
            if cfg.drop_wrong_citations:
                answer = drop_wrong(answer, checks)
                checks = [c for c in checks if c.status != "wrong"]
    return PipelineResult(
        question=question,
        answer=answer,
        hits=hits,
        checks=checks,
        rewrite=retriever.last_rewrite,
        timings_ms=timings,
        usage=log,
    )


def drop_wrong(answer: Answer, checks: list[CitationCheck]) -> Answer:
    """Remove citations judged wrong and strip their [n] markers; renumber the rest."""
    keep = [c.index for c in checks if c.status != "wrong"]
    renumber = {old: new for new, old in enumerate(keep, start=1)}
    text = answer.answer
    for c in checks:
        marker = f"[{c.index}]"
        text = text.replace(marker, f"[@{renumber[c.index]}]" if c.index in renumber else "")
    text = text.replace("[@", "[")
    for c in checks:
        c.index = renumber.get(c.index, c.index)
    citations = [answer.citations[i - 1] for i in keep if i - 1 < len(answer.citations)]
    return answer.model_copy(update={"answer": " ".join(text.split()), "citations": citations})
