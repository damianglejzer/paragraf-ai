"""Retrieval evaluation: recall@k and MRR for each retrieval mode.

Usage: uv run python -m paragraf.evaluation.run_retrieval [--modes naive,hybrid] [--limit N]
Writes evals/results/retrieval.json and evals/results/retrieval.md.
"""

import argparse
import json
import logging
import time
from typing import Any, cast

from paragraf.config import REPO_ROOT, get_settings
from paragraf.db import repository as repo
from paragraf.evaluation.dataset import EvalItem, load_dataset
from paragraf.evaluation.metrics import mean, percentile, recall_at_k, reciprocal_rank
from paragraf.providers.factory import make_embedder, make_llm, make_reranker
from paragraf.retrieval.rewrite import QueryRewriter
from paragraf.retrieval.search import Mode, Retriever

log = logging.getLogger("paragraf.eval.retrieval")
RESULTS_DIR = REPO_ROOT / "evals" / "results"
KS = (1, 3, 5, 10)
ALL_MODES: list[Mode] = ["naive", "vector", "fulltext", "hybrid", "hybrid_rerank", "full"]


def evaluate_mode(retriever: Retriever, items: list[EvalItem], mode: Mode) -> dict[str, Any]:
    per_item: list[dict[str, Any]] = []
    latencies: list[float] = []
    for item in items:
        start = time.perf_counter()
        hits = retriever.search(item.question, k=max(KS), mode=mode)
        latencies.append((time.perf_counter() - start) * 1000)
        ranked = [h.ids for h in hits]
        per_item.append(
            {
                "id": item.id,
                "category": item.category,
                **{f"recall@{k}": recall_at_k(ranked, item.expected_ids, k) for k in KS},
                "mrr": reciprocal_rank(ranked, item.expected_ids),
                "recall@5_unit": recall_at_k(ranked, item.expected_ids, 5, level="unit"),
            }
        )

    def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
        keys = [f"recall@{k}" for k in KS] + ["mrr", "recall@5_unit"]
        return {key: round(mean([r[key] for r in rows]), 4) for key in keys}

    categories = sorted({r["category"] for r in per_item})
    return {
        "mode": mode,
        "n": len(per_item),
        "overall": summarize(per_item),
        "by_category": {
            c: summarize([r for r in per_item if r["category"] == c]) for c in categories
        },
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 1),
            "p95": round(percentile(latencies, 95), 1),
        },
        "items": per_item,
    }


def to_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "| Mode | R@1 | R@3 | R@5 | R@10 | MRR | R@5 (exact unit) | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        o = r["overall"]
        lines.append(
            f"| {r['mode']} | {o['recall@1']:.3f} | {o['recall@3']:.3f} | {o['recall@5']:.3f} | "
            f"{o['recall@10']:.3f} | {o['mrr']:.3f} | {o['recall@5_unit']:.3f} | "
            f"{r['latency_ms']['p50']} | {r['latency_ms']['p95']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default=",".join(ALL_MODES))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    items = [i for i in load_dataset() if i.expected_ids]
    if args.limit:
        items = items[: args.limit]
    settings = get_settings()
    results = []
    with repo.connect() as conn:
        retriever = Retriever(
            conn,
            make_embedder(settings),
            make_reranker(settings),
            rewriter=QueryRewriter(make_llm(settings)),
        )
        for mode in args.modes.split(","):
            log.info("evaluating %s on %d questions", mode, len(items))
            res = evaluate_mode(retriever, items, cast(Mode, mode))
            log.info("%s: %s", mode, res["overall"])
            results.append(res)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "embedding_model": settings.embedding_model,
        "reranker": f"{settings.reranker_provider}:{settings.reranker_model}",
        "n_questions": len(items),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (RESULTS_DIR / "retrieval.json").write_text(
        json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=1)
    )
    (RESULTS_DIR / "retrieval.md").write_text(to_markdown(results))
    print(to_markdown(results))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    main()
