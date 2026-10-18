"""Precompute answers for the example questions so the demo answers them instantly.

Usage (with the API running): uv run python -m paragraf.api.warm_cache [--url http://localhost:8010]
"""

import argparse
import json

import httpx

from paragraf.api.main import EXAMPLES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8010")
    args = parser.parse_args()
    for example in EXAMPLES:
        question = example["question"]
        final = None
        with httpx.stream(
            "POST", f"{args.url}/api/chat", json={"question": question}, timeout=120
        ) as resp:
            event = ""
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event in ("final", "error"):
                    final = (event, json.loads(line[5:]))
        if final and final[0] == "final":
            data = final[1]
            statuses = [c["status"] for c in data["citations"]]
            print(
                f"OK   {example['label']:<14} {data['status']:<8} cytaty={statuses} "
                f"{'(cache)' if data['cached'] else f'{data["metrics"]["total_ms"]} ms'}"
            )
        else:
            print(f"FAIL {example['label']:<14} {final}")


if __name__ == "__main__":
    main()
