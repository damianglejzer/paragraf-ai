import json
import math

import pytest

from paragraf.evaluation.dataset import EvalItem
from paragraf.evaluation.run_all import build_report
from paragraf.evaluation.run_generation import stratified


def test_report_drops_per_question_rows_and_nan() -> None:
    retrieval = {
        "meta": {"n_questions": 2},
        "results": [{"mode": "full", "overall": {"mrr": math.nan}, "items": [{"id": "q1"}]}],
    }
    generation = {
        "meta": {"llm": "m"},
        "results": [{"config": "naive", "summary": {"correctness": 0.5}, "items": [{}]}],
    }
    report = build_report({"n": 2}, retrieval, generation)
    assert "items" not in report["retrieval"][0]
    assert "items" not in report["generation"][0]
    assert report["retrieval"][0]["overall"]["mrr"] is None
    assert report["meta"] == {"n_questions": 2, "llm": "m"}
    json.loads(json.dumps(report, allow_nan=False))  # valid JSON for the browser


def test_stratified_keeps_every_category() -> None:
    items = [
        EvalItem(id=f"r{i}", question="?", reference_answer="", category="regular")
        for i in range(8)
    ] + [EvalItem(id="o1", question="?", reference_answer="", category="out_of_scope")]
    subset = stratified(items, 4)
    assert {i.category for i in subset} == {"regular", "out_of_scope"}
    assert len(subset) < len(items)


def test_jina_reranker_retries_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from paragraf.providers import jina, rerankers

    statuses = [429, 429, 200]

    def handler(_: httpx.Request) -> httpx.Response:
        code = statuses.pop(0)
        body = {"results": [{"index": 1, "relevance_score": 0.9}], "usage": {"total_tokens": 3}}
        return httpx.Response(code, json=body if code == 200 else {})

    monkeypatch.setattr(jina.time, "sleep", lambda _s: None)
    reranker = rerankers.JinaReranker("key", "model", retries=2)
    reranker._http = httpx.Client(transport=httpx.MockTransport(handler))
    assert reranker.rerank("q", ["a", "b"], 1) == [(1, 0.9)]
    assert statuses == []
