"""Settings for the query and reranking service."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class QuerySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    openrouter_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str | None = None
    openrouter_chat_model: str = "nvidia/nemotron-3.5-lightning:free"
    openrouter_chat_fallback_models: str = "openrouter/free"
    openrouter_rerank_model: str = "nvidia/llama-nemotron-rerank-vl-1b-v2:free"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gpt-oss:20b"
    ollama_timeout_seconds: int = 300
    rerank_provider: str = "openrouter"
    ollama_rerank_model: str = "gpt-oss:20b"
    query_llm_provider: str = "ollama"
    top_k: int = 5
    retrieval_candidate_k: int = 30
    rerank_candidate_k: int = 20
    rrf_k: int = 60
    max_history_turns: int = 8
    rag_vu_api_base_url: str = "http://localhost:8080"


settings = QuerySettings()
