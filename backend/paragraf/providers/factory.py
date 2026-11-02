"""Build providers from settings (.env). Swapping a vendor is a config change."""

from functools import lru_cache
from typing import Literal

from paragraf.config import Settings, get_settings
from paragraf.providers.base import LLM, Embedder, Reranker
from paragraf.providers.cache import DiskCache
from paragraf.providers.fake import FakeEmbedder, FakeLLM, FakeReranker


@lru_cache
def _cache(name: str) -> DiskCache:
    return DiskCache(get_settings().data_dir / "cache" / f"{name}.sqlite")


def _require(value: str, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} is not set; add it to .env or use the 'fake' provider")
    return value


def make_embedder(settings: Settings | None = None, *, retries: int = 1) -> Embedder:
    """`retries`: how many times to retry a rate-limited request (batch evals pass more)."""
    s = settings or get_settings()
    if s.embedding_provider == "fake":
        return FakeEmbedder(s.embedding_dim)
    if s.embedding_provider == "gemini":
        from paragraf.providers.gemini import GeminiEmbedder

        return GeminiEmbedder(
            _require(s.gemini_api_key, "GEMINI_API_KEY"),
            s.embedding_model,
            s.embedding_dim,
            _cache("embeddings"),
        )
    if s.embedding_provider == "jina":
        from paragraf.providers.jina import JinaEmbedder

        return JinaEmbedder(
            _require(s.jina_api_key, "JINA_API_KEY"),
            s.embedding_model,
            s.embedding_dim,
            _cache("embeddings"),
            retries=retries,
        )
    raise ValueError(f"unknown EMBEDDING_PROVIDER={s.embedding_provider}")


def make_llm(
    settings: Settings | None = None, *, role: Literal["answer", "judge"] = "answer"
) -> LLM:
    """`answer`: main generation model. `judge`: small fast model (verification, reranking)."""
    s = settings or get_settings()
    if s.llm_provider == "fake":
        return FakeLLM()
    model, thinking = (
        (s.llm_model, s.llm_thinking) if role == "answer" else (s.judge_model, s.judge_thinking)
    )
    if s.llm_provider == "openai":
        from paragraf.providers.openai_llm import OpenAILLM

        return OpenAILLM(
            _require(s.openai_api_key, "OPENAI_API_KEY"), model, _cache("llm"), thinking or None
        )
    if s.llm_provider == "gemini":
        from paragraf.providers.gemini import GeminiLLM

        return GeminiLLM(
            _require(s.gemini_api_key, "GEMINI_API_KEY"), model, _cache("llm"), thinking or None
        )
    raise ValueError(f"unknown LLM_PROVIDER={s.llm_provider}")


def make_reranker(settings: Settings | None = None, *, retries: int = 1) -> Reranker:
    """`retries`: how many times to retry a rate-limited request (batch evals pass more)."""
    s = settings or get_settings()
    match s.reranker_provider:
        case "fake":
            return FakeReranker()
        case "none":
            from paragraf.providers.rerankers import NoReranker

            return NoReranker()
        case "jina":
            from paragraf.providers.rerankers import JinaReranker

            return JinaReranker(
                _require(s.jina_api_key, "JINA_API_KEY"),
                s.reranker_model,
                _cache("rerank"),
                retries=retries,
            )
        case "llm":
            from paragraf.providers.rerankers import LLMReranker

            return LLMReranker(make_llm(s, role="judge"))
    raise ValueError(f"unknown RERANKER_PROVIDER={s.reranker_provider}")
