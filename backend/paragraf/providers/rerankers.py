"""Reranker implementations: Jina API, LLM-as-reranker (Gemini), and a no-op."""

import httpx
from pydantic import BaseModel, Field

from paragraf.providers.base import LLM, ProviderUnavailable
from paragraf.providers.cache import DiskCache


class NoReranker:
    name = "none"

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        return [(i, 1.0 / (i + 1)) for i in range(min(top_n, len(documents)))]


class JinaReranker:
    """Cross-encoder via https://api.jina.ai/v1/rerank (free token pool on new keys)."""

    name = "jina"
    URL = "https://api.jina.ai/v1/rerank"

    def __init__(self, api_key: str, model: str, cache: DiskCache | None = None) -> None:
        self._http = httpx.Client(timeout=30.0, headers={"Authorization": f"Bearer {api_key}"})
        self.model = model
        self._cache = cache

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        key = DiskCache.key("rerank", self.model, query, documents, top_n)
        if self._cache and (hit := self._cache.get(key)) is not None:
            return [(int(i), float(s)) for i, s in hit]
        resp = self._http.post(
            self.URL,
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": False,
            },
        )
        if resp.status_code in (402, 429):
            raise ProviderUnavailable(f"Jina reranker unavailable: {resp.status_code}")
        resp.raise_for_status()
        result = [(r["index"], r["relevance_score"]) for r in resp.json()["results"]]
        if self._cache:
            self._cache.set(key, result)
        return result


class _Ranking(BaseModel):
    ranking: list[int] = Field(description="Candidate numbers, most relevant first")


RERANK_SYSTEM = (
    "You rank Polish legal provisions by how directly they answer a user's question. "
    "Return only candidate numbers, most relevant first. Omit clearly irrelevant ones."
)


class LLMReranker:
    """Listwise reranking with a cheap LLM. Free fallback when no cross-encoder quota is left."""

    name = "llm"

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        listing = "\n\n".join(f"[{i}] {doc[:700]}" for i, doc in enumerate(documents))
        prompt = f"Pytanie: {query}\n\nKandydaci:\n{listing}\n\nZwróć {top_n} najlepszych."
        resp = self._llm.complete(RERANK_SYSTEM, prompt, json_schema=_Ranking)
        order = [
            i for i in _Ranking.model_validate_json(resp.text).ranking if 0 <= i < len(documents)
        ]
        seen: list[int] = list(dict.fromkeys(order))
        seen += [i for i in range(len(documents)) if i not in seen]  # keep recall if LLM omits
        return [(i, 1.0 / (rank + 1)) for rank, i in enumerate(seen[:top_n])]
