"""Run the whole eval suite and write the frontend's report (frontend/src/data/eval-report.json).

The frontend bundles the report at build time, so the results page needs no backend call.

Usage: uv run python -m paragraf.evaluation.run_all [--limit N]

Deliberately small: on the ~33-question dataset this is roughly 200 LLM calls (retrieval: one
rewrite per question; generation: three configs, see run_generation), a few minutes and a few
cents. LLM responses are cached on disk, so a re-run after a failure only pays for the calls
that did not finish. After a run, rebuild/redeploy the frontend to publish the new report.
"""

import argparse
import json
import logging
import math
import time
from collections import Counter
from typing import Any

from paragraf.config import REPO_ROOT
from paragraf.evaluation import run_generation, run_retrieval
from paragraf.evaluation.dataset import load_dataset

log = logging.getLogger("paragraf.eval")
REPORT = REPO_ROOT / "frontend" / "src" / "data" / "eval-report.json"


def without_nan(value: Any) -> Any:
    """NaN (an empty mean) is not valid JSON for browsers; emit null instead."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: without_nan(v) for k, v in value.items()}
    if isinstance(value, list):
        return [without_nan(v) for v in value]
    return value


def build_report(
    items_meta: dict[str, Any], retrieval: dict[str, Any], generation: dict[str, Any]
) -> dict[str, Any]:
    """Frontend payload: summaries only, per-question rows stay in the per-suite files."""
    report = {
        "meta": {**retrieval["meta"], **generation["meta"]},
        "dataset": items_meta,
        "retrieval": [{k: v for k, v in r.items() if k != "items"} for r in retrieval["results"]],
        "generation": [{k: v for k, v in g.items() if k != "items"} for g in generation["results"]],
    }
    return dict(without_nan(report))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="stratified subset for a dry run")
    args = parser.parse_args()
    items = load_dataset()
    if args.limit:
        items = run_generation.stratified(items, args.limit)
    started = time.perf_counter()

    retrieval = run_retrieval.run(items, run_retrieval.ALL_MODES)
    generation = run_generation.run(items, list(run_generation.CONFIGS))

    dataset = {
        "n": len(items),
        "by_category": dict(Counter(i.category for i in items)),
        "verified": sum(i.verified for i in items),
    }
    report = build_report(dataset, retrieval, generation)
    report["meta"]["duration_s"] = round(time.perf_counter() - started)

    out = run_retrieval.RESULTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "retrieval.json").write_text(json.dumps(retrieval, ensure_ascii=False, indent=1))
    (out / "generation.json").write_text(
        json.dumps(generation, ensure_ascii=False, indent=1, default=str)
    )
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n")
    log.info("wrote %s in %d s", REPORT, report["meta"]["duration_s"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    main()
