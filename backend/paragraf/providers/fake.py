"""Deterministic offline providers for tests and CI (no API keys, no network).

The fake embedder is a hashed bag of lowercase word stems, so lexical overlap still yields
sensible similarity and retrieval tests stay meaningful.
"""

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterator

from pydantic import BaseModel

from paragraf.providers.base import EmbedTask, LLMResponse, Usage


def _stem(word: str) -> str:
    return word[:5]


class FakeEmbedder:
    name = "fake"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in re.findall(r"\w+", text.lower()):
            if len(word) < 3:
                continue
            h = int(hashlib.md5(_stem(word).encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeReranker:
    """Scores by word-stem overlap with the query."""

    name = "fake"

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        q = {_stem(w) for w in re.findall(r"\w+", query.lower()) if len(w) >= 3}
        scores = []
        for i, doc in enumerate(documents):
            d = {_stem(w) for w in re.findall(r"\w+", doc.lower()) if len(w) >= 3}
            scores.append((i, len(q & d) / (len(q) or 1)))
        return sorted(scores, key=lambda s: -s[1])[:top_n]


class FakeLLM:
    """Returns canned output. Tests can inject a `responder` to script answers."""

    name = "fake"
    model = "fake-llm"

    def __init__(self, responder: Callable[[str, str], str] | None = None) -> None:
        self._responder = responder

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        json_schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if self._responder is not None:
            text = self._responder(system, prompt)
        elif json_schema is not None:
            text = json.dumps(_minimal_instance(json_schema.model_json_schema()))
        else:
            text = "To jest odpowiedź testowa."
        return LLMResponse(
            text=text,
            model=self.model,
            usage=Usage(input_tokens=len(prompt) // 4, output_tokens=len(text) // 4),
        )

    def stream(self, system: str, prompt: str, *, temperature: float = 0.0) -> Iterator[str]:
        text = self.complete(system, prompt).text
        for i in range(0, len(text), 8):
            yield text[i : i + 8]


def _minimal_instance(schema: dict[str, object]) -> object:
    defs = schema.get("$defs", {})

    def build(s: dict[str, object]) -> object:
        if "$ref" in s:
            return build(defs[str(s["$ref"]).split("/")[-1]])  # type: ignore[index]
        if "enum" in s:
            return s["enum"][0]  # type: ignore[index]
        if "anyOf" in s:
            return build(s["anyOf"][0])  # type: ignore[index]
        kind = s.get("type")
        if kind == "object":
            props: dict[str, dict[str, object]] = s.get("properties", {})  # type: ignore[assignment]
            return {k: build(v) for k, v in props.items()}
        return {"array": [], "string": "", "integer": 0, "number": 0.0, "boolean": False}.get(
            str(kind)
        )

    return build(schema)
