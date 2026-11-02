"""Application settings loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql://paragraf:paragraf@localhost:5434/paragraf"
    data_dir: Path = REPO_ROOT / "data"
    eli_base_url: str = "https://api.sejm.gov.pl/eli"

    llm_provider: str = "fake"
    llm_model: str = "gpt-5.4-mini"
    # reasoning effort (OpenAI) / thinking level (Gemini); empty = model default
    llm_thinking: str = "none"
    judge_model: str = "gpt-5.4-nano"
    judge_thinking: str = "low"
    embedding_provider: str = "fake"
    embedding_model: str = "jina-embeddings-v3"
    embedding_dim: int = 768
    reranker_provider: str = "none"
    reranker_model: str = "jina-reranker-v2-base-multilingual"

    openai_api_key: str = ""
    gemini_api_key: str = ""
    jina_api_key: str = ""

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    rate_limit_per_minute: int = 6
    daily_request_budget: int = 300
    max_query_chars: int = 500
    cors_origins: str = "http://localhost:5173"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()
