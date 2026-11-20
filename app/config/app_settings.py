"""All configuration, read from the environment and ``.env``."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://rag_vu_user:rag_vu_password@rag_vu-postgres:5432/rag_vu_db"
)
DEFAULT_DATABASE_URL_SYNC = (
    "postgresql://rag_vu_user:rag_vu_password@rag_vu-postgres:5432/rag_vu_db"
)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = DEFAULT_DATABASE_URL
    database_url_sync: str = DEFAULT_DATABASE_URL_SYNC
    database_echo: bool = False
    upload_path: str = "./media/documents"

    celery_broker_url: str = "redis://redis:6379/0"
    event_batch_size: int = 100
    event_poll_interval_seconds: float = 1.0
    inbox_lock_timeout_seconds: int = 3600
    inbox_redelivery_after_seconds: int = 300

    embedding_provider: str = "openrouter"
    embedding_batch_size: int = 32
    embedding_chunk_max_tokens: int = 512
    openrouter_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str | None = None
    openrouter_embedding_model: str = "nvidia/nemotron-3-embed-1b:free"
    openrouter_embedding_tokenizer: str = "nvidia/Nemotron-3-Embed-1B-BF16"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_embedding_tokenizer: str = "Qwen/Qwen3-Embedding-0.6B"

    query_llm_provider: str = "ollama"
    rerank_provider: str = "openrouter"
    openrouter_chat_model: str = "nvidia/nemotron-3.5-lightning:free"
    openrouter_chat_fallback_models: str = "openrouter/free"
    openrouter_rerank_model: str = "nvidia/llama-nemotron-rerank-vl-1b-v2:free"
    ollama_model: str = "gpt-oss:20b"
    ollama_rerank_model: str = "gpt-oss:20b"
    ollama_timeout_seconds: int = 300
    top_k: int = 5
    retrieval_candidate_k: int = 30
    rerank_candidate_k: int = 20
    rrf_k: int = 60
    max_history_turns: int = 8
    rag_vu_api_base_url: str = "http://localhost:8080"

    # Arize Phoenix tracing; off unless enabled, so tests and CLI tools export nothing.
    tracing_enabled: bool = False
    phoenix_collector_endpoint: str = "http://phoenix:6006/v1/traces"
    phoenix_project_name: str = "rag_vu"

    @property
    def normalized_embedding_provider(self) -> str:
        provider = self.embedding_provider.strip().lower()
        if provider not in {"openrouter", "ollama"}:
            raise ValueError("EMBEDDING_PROVIDER must be 'openrouter' or 'ollama'.")
        return provider

    @property
    def embedding_model(self) -> str:
        """The embedding model of the configured provider."""
        if self.normalized_embedding_provider == "ollama":
            return self.ollama_embedding_model.strip()
        return self.openrouter_embedding_model.strip()

    @property
    def embedding_tokenizer(self) -> str:
        """The Hugging Face tokenizer matching the configured embedding model."""
        if self.normalized_embedding_provider == "ollama":
            return self.ollama_embedding_tokenizer.strip()
        return self.openrouter_embedding_tokenizer.strip()


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
