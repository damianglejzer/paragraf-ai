"""OpenAI LLM provider (Chat Completions) via the official `openai` SDK."""

from collections.abc import Iterator
from typing import Any

import openai
from pydantic import BaseModel

from paragraf.providers import usage
from paragraf.providers.base import LLMResponse, ProviderUnavailable, Usage
from paragraf.providers.cache import DiskCache

# Still failing after the SDK's own retries: the demo degrades gracefully instead of crashing.
TRANSIENT = (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)


class OpenAILLM:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        cache: DiskCache | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        # The SDK retries 429/5xx with backoff on its own; two retries keep a chat request snappy.
        self._client = openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=2)
        self.model = model
        self._cache = cache
        # GPT-5 family models reason by default; "none"/"low" keeps latency around 1-3 s.
        self._reasoning = reasoning_effort or None

    def _params(self, system: str, prompt: str, temperature: float) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if self._reasoning:
            # Reasoning models accept only the default temperature.
            params["reasoning_effort"] = self._reasoning
        else:
            params["temperature"] = temperature
        return params

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        json_schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        schema = json_schema.model_json_schema() if json_schema else None
        key = DiskCache.key("llm", self.model, self._reasoning, system, prompt, schema, temperature)
        if self._cache and (hit := self._cache.get(key)):
            cached = LLMResponse.model_validate({**hit, "cached": True})
            usage.record(self.model, cached.usage.input_tokens, cached.usage.output_tokens, True)
            return cached
        params = self._params(system, prompt, temperature)
        if json_schema and schema:
            # Non-strict: our Pydantic schemas use defaults and bounds that strict mode rejects;
            # callers validate the JSON with the same model anyway.
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": json_schema.__name__, "schema": schema, "strict": False},
            }
        try:
            resp = self._client.chat.completions.create(**params)
        except TRANSIENT as exc:
            raise ProviderUnavailable(f"OpenAI unavailable: {exc}") from exc
        meta = resp.usage
        result = LLMResponse(
            text=resp.choices[0].message.content or "",
            model=self.model,
            usage=Usage(
                input_tokens=meta.prompt_tokens if meta else 0,
                output_tokens=meta.completion_tokens if meta else 0,
            ),
        )
        usage.record(self.model, result.usage.input_tokens, result.usage.output_tokens)
        if self._cache:
            self._cache.set(key, result.model_dump())
        return result

    def stream(self, system: str, prompt: str, *, temperature: float = 0.0) -> Iterator[str]:
        try:
            chunks = self._client.chat.completions.create(
                **self._params(system, prompt, temperature), stream=True
            )
            for chunk in chunks:
                if chunk.choices and (text := chunk.choices[0].delta.content):
                    yield text
        except openai.RateLimitError as exc:
            raise ProviderUnavailable("OpenAI rate limit") from exc
