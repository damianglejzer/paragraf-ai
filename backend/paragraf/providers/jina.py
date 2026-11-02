"""Jina AI embeddings (jina-embeddings-v3, multilingual, Matryoshka dimensions)."""

import time
from typing import Any

import httpx

from paragraf.providers import usage
from paragraf.providers.base import EmbedTask, ProviderUnavailable
from paragraf.providers.cache import DiskCache


def post_with_retry(
    http: httpx.Client, url: str, payload: dict[str, Any], retries: int
) -> httpx.Response:
    """POST, retrying 429 with exponential backoff. The free tier limits requests per minute and
    concurrency, so interactive calls retry once and batch evals more patiently. 402 (token pool
    exhausted) is returned as is and never retried."""
    delay = 3.0
    for attempt in range(retries + 1):
        resp = http.post(url, json=payload)
        if resp.status_code != 429 or attempt == retries:
            return resp
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


class JinaEmbedder:
    name = "jina"
    URL = "https://api.jina.ai/v1/embeddings"
    BATCH = 128

    def __init__(
        self, api_key: str, model: str, dim: int, cache: DiskCache | None = None, retries: int = 1
    ) -> None:
        self._http = httpx.Client(timeout=60.0, headers={"Authorization": f"Bearer {api_key}"})
        self.model = model
        self.dim = dim
        self._cache = cache
        self._retries = retries

    def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        jina_task = "retrieval.passage" if task == "document" else "retrieval.query"
        keys = [DiskCache.key("emb", self.model, self.dim, jina_task, t) for t in texts]
        found = self._cache.get_many(keys) if self._cache else {}
        missing = [i for i, k in enumerate(keys) if k not in found]
        for start in range(0, len(missing), self.BATCH):
            idx = missing[start : start + self.BATCH]
            payload = {
                "model": self.model,
                "task": jina_task,
                "dimensions": self.dim,
                "normalized": True,
                "input": [texts[i] for i in idx],
            }
            resp = post_with_retry(self._http, self.URL, payload, self._retries)
            if resp.status_code in (402, 429):
                raise ProviderUnavailable(f"Jina embeddings unavailable: {resp.status_code}")
            resp.raise_for_status()
            body = resp.json()
            usage.record(self.model, int(body.get("usage", {}).get("total_tokens", 0)))
            data = sorted(body["data"], key=lambda d: d["index"])
            new = {keys[i]: d["embedding"] for i, d in zip(idx, data, strict=True)}
            found.update(new)
            if self._cache:
                self._cache.set_many(new)
        return [found[k] for k in keys]
