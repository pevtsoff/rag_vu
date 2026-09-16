from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+asyncpg://rag_vu_user:rag_vu_password@rag_vu-postgres:5432/rag_vu_db"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql://rag_vu_user:rag_vu_password@rag_vu-postgres:5432/rag_vu_db"
    )
    EMBEDDING_DIM: int = 1536
    EMBEDDING_PROVIDER: str = "openrouter"
    OPENROUTER_EMBEDDING_MODEL: str = "nvidia/nemotron-3-embed-1b:free"
    OPENROUTER_EMBEDDING_TOKENIZER: str = "nvidia/Nemotron-3-Embed-1B-BF16"
    OLLAMA_EMBEDDING_MODEL: str = "qwen3-embedding:0.6b"
    OLLAMA_EMBEDDING_TOKENIZER: str = "Qwen/Qwen3-Embedding-0.6B"
    EMBEDDING_CHUNK_MAX_TOKENS: int = 512

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
