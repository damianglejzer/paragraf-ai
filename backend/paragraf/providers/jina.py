"""Jina AI embeddings (jina-embeddings-v3, multilingual, Matryoshka dimensions)."""

import httpx

from paragraf.providers.base import EmbedTask, ProviderUnavailable
from paragraf.providers.cache import DiskCache


class JinaEmbedder:
    name = "jina"
    URL = "https://api.jina.ai/v1/embeddings"
    BATCH = 128

    def __init__(self, api_key: str, model: str, dim: int, cache: DiskCache | None = None) -> None:
        self._http = httpx.Client(timeout=60.0, headers={"Authorization": f"Bearer {api_key}"})
        self.model = model
        self.dim = dim
        self._cache = cache

    def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        jina_task = "retrieval.passage" if task == "document" else "retrieval.query"
        keys = [DiskCache.key("emb", self.model, self.dim, jina_task, t) for t in texts]
        found = self._cache.get_many(keys) if self._cache else {}
        missing = [i for i, k in enumerate(keys) if k not in found]
        for start in range(0, len(missing), self.BATCH):
            idx = missing[start : start + self.BATCH]
            resp = self._http.post(
                self.URL,
                json={
                    "model": self.model,
                    "task": jina_task,
                    "dimensions": self.dim,
                    "normalized": True,
                    "input": [texts[i] for i in idx],
                },
            )
            if resp.status_code in (402, 429):
                raise ProviderUnavailable(f"Jina embeddings unavailable: {resp.status_code}")
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            new = {keys[i]: d["embedding"] for i, d in zip(idx, data, strict=True)}
            found.update(new)
            if self._cache:
                self._cache.set_many(new)
        return [found[k] for k in keys]
