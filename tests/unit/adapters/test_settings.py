import pytest

from app.adapters.outbound.persistence.vector_columns import vector_column_for
from app.config.app_settings import AppSettings


def test_tokenizer_tracks_the_embedding_provider() -> None:
    assert (
        AppSettings(embedding_provider="ollama").embedding_tokenizer == "Qwen/Qwen3-Embedding-0.6B"
    )
    assert (
        AppSettings(embedding_provider=" OpenRouter ").embedding_tokenizer
        == "nvidia/Nemotron-3-Embed-1B-BF16"
    )
    with pytest.raises(ValueError):
        _ = AppSettings(embedding_provider="other").embedding_tokenizer


def test_vector_column_is_chosen_by_dimension() -> None:
    assert vector_column_for(768) == "embedding_small"
    assert vector_column_for(2048) == "embedding_big"
    with pytest.raises(ValueError):
        vector_column_for(5)


def test_embedding_model_tracks_the_embedding_provider() -> None:
    assert AppSettings(embedding_provider="ollama").embedding_model == "qwen3-embedding:0.6b"
    assert (
        AppSettings(embedding_provider="openrouter").embedding_model
        == "nvidia/nemotron-3-embed-1b:free"
    )


def test_tracing_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRACING_ENABLED", raising=False)
    assert AppSettings(_env_file=None).tracing_enabled is False
