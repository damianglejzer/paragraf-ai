"""Provider interfaces. Concrete implementations are chosen from .env via `providers.factory`."""

from collections.abc import Iterator
from typing import Literal, Protocol

from pydantic import BaseModel

EmbedTask = Literal["document", "query"]


class ProviderUnavailable(RuntimeError):
    """The provider refused the request (rate limit / quota). The demo degrades gracefully."""


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class LLMResponse(BaseModel):
    text: str
    model: str
    usage: Usage = Usage()
    cached: bool = False


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]: ...


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        """Return (index into `documents`, score) pairs, best first."""
        ...


class LLM(Protocol):
    name: str
    model: str

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        json_schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Single completion. With `json_schema`, `text` is JSON valid against the schema."""
        ...

    def stream(self, system: str, prompt: str, *, temperature: float = 0.0) -> Iterator[str]: ...
