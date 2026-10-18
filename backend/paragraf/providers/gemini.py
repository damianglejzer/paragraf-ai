"""Google Gemini (free tier) LLM and embedding providers via the `google-genai` SDK."""

import math
import threading
import time
from collections.abc import Iterator
from typing import Any, ClassVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from paragraf.providers.base import EmbedTask, LLMResponse, ProviderUnavailable, Usage
from paragraf.providers.cache import DiskCache


class _RateLimiter:
    """Client-side pacing per model, so parallel workers stay under the free-tier RPM."""

    _locks: ClassVar[dict[str, threading.Lock]] = {}
    _next_slot: ClassVar[dict[str, float]] = {}

    @classmethod
    def wait(cls, model: str, rpm: int) -> None:
        lock = cls._locks.setdefault(model, threading.Lock())
        with lock:
            now = time.monotonic()
            slot = max(now, cls._next_slot.get(model, now))
            cls._next_slot[model] = slot + 60.0 / rpm
        if slot > now:
            time.sleep(slot - now)


def _call_with_backoff(fn: Any, *args: Any, attempts: int = 4, **kwargs: Any) -> Any:
    """Retry 429/5xx with exponential backoff. Free-tier quotas are tight."""
    delay = 4.0
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except errors.APIError as exc:
            retryable = exc.code == 429 or (exc.code or 0) >= 500
            if not retryable:
                raise
            if attempt == attempts - 1:
                raise ProviderUnavailable(f"Gemini unavailable: {exc.code} {exc.message}") from exc
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


class GeminiEmbedder:
    name = "gemini"
    BATCH = 100

    def __init__(self, api_key: str, model: str, dim: int, cache: DiskCache | None = None) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.dim = dim
        self._cache = cache

    def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        task_type = "RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY"
        keys = [DiskCache.key("emb", self.model, self.dim, task_type, t) for t in texts]
        found = self._cache.get_many(keys) if self._cache else {}
        missing = [i for i, k in enumerate(keys) if k not in found]
        for start in range(0, len(missing), self.BATCH):
            idx = missing[start : start + self.BATCH]
            resp = _call_with_backoff(
                self._client.models.embed_content,
                model=self.model,
                # One Content per text: a plain list of strings is merged into a single
                # multimodal input by gemini-embedding-2 and yields one vector.
                contents=[types.Content(parts=[types.Part(text=texts[i])]) for i in idx],
                config=types.EmbedContentConfig(
                    task_type=task_type, output_dimensionality=self.dim
                ),
            )
            new = {keys[i]: _normalize(e.values) for i, e in zip(idx, resp.embeddings, strict=True)}
            found.update(new)
            if self._cache:
                self._cache.set_many(new)
        return [found[k] for k in keys]


def _normalize(values: list[float] | None) -> list[float]:
    # Truncated (Matryoshka) Gemini embeddings are not unit-length; normalize for cosine/IP.
    vals = values or []
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


class GeminiLLM:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        cache: DiskCache | None = None,
        thinking_level: str | None = None,
        rpm: int = 14,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._cache = cache
        self._rpm = rpm
        # Gemini 3 thinks by default; "minimal"/"low" keeps latency around 1-3 s.
        self._thinking = (
            types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None
        )

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        json_schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        key = DiskCache.key(
            "llm",
            self.model,
            system,
            prompt,
            json_schema.model_json_schema() if json_schema else None,
            temperature,
        )
        if self._cache and (hit := self._cache.get(key)):
            return LLMResponse.model_validate({**hit, "cached": True})
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_schema else None,
            response_json_schema=json_schema.model_json_schema() if json_schema else None,
            thinking_config=self._thinking,
        )
        _RateLimiter.wait(self.model, self._rpm)
        resp = _call_with_backoff(
            self._client.models.generate_content, model=self.model, contents=prompt, config=config
        )
        meta = resp.usage_metadata
        result = LLMResponse(
            text=resp.text or "",
            model=self.model,
            usage=Usage(
                input_tokens=(meta.prompt_token_count or 0) if meta else 0,
                output_tokens=(meta.candidates_token_count or 0) if meta else 0,
            ),
        )
        if self._cache:
            self._cache.set(key, result.model_dump())
        return result

    def stream(self, system: str, prompt: str, *, temperature: float = 0.0) -> Iterator[str]:
        config = types.GenerateContentConfig(
            system_instruction=system, temperature=temperature, thinking_config=self._thinking
        )
        _RateLimiter.wait(self.model, self._rpm)
        try:
            for chunk in self._client.models.generate_content_stream(
                model=self.model, contents=prompt, config=config
            ):
                if chunk.text:
                    yield chunk.text
        except errors.APIError as exc:
            if exc.code == 429:
                raise ProviderUnavailable("Gemini rate limit") from exc
            raise
