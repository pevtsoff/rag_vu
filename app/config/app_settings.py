"""All configuration, read from the environment and ``.env``."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.versioning.versioning_thresholds import VersioningThresholds

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
    # gpt-oss (and other hidden-reasoning models) spend part of this budget on internal
    # reasoning before the visible answer; too low and Ollama truncates with no content at
    # all, 200 OK and done_reason="length" (see OllamaChatModel._completion).
    ollama_max_answer_tokens: int = 2000
    top_k: int = 5
    retrieval_candidate_k: int = 30
    rerank_candidate_k: int = 20
    rrf_k: int = 60
    max_history_turns: int = 8
    rag_vu_api_base_url: str = "http://localhost:8080"

    # Document versioning (docs/tasks/deduplication.md): cosine similarity on a 0..1 scale.
    versioning_sem_sim: float = 0.96
    versioning_duplicate_sem_sim: float = 0.995
    versioning_lex_sim_min: float = 0.5
    versioning_duplicate_lex_sim: float = 0.99

    # Multi-version retrieval (latest_only=False).
    multi_version_overfetch: int = 4
    k_per_version: int = 2
    version_relevance_floor: float = 0.6
    max_versions: int = 4
    multi_version_chunk_budget: int = 10

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
    def versioning_thresholds(self) -> VersioningThresholds:
        return VersioningThresholds(
            semantic=self.versioning_sem_sim,
            duplicate_semantic=self.versioning_duplicate_sem_sim,
            lexical_min=self.versioning_lex_sim_min,
            duplicate_lexical=self.versioning_duplicate_lex_sim,
        )

    @property
    def embedding_tokenizer(self) -> str:
        """The Hugging Face tokenizer matching the configured embedding model."""
        if self.normalized_embedding_provider == "ollama":
            return self.ollama_embedding_tokenizer.strip()
        return self.openrouter_embedding_tokenizer.strip()


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
