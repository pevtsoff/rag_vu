"""The composition root switches tracing on and off and wraps every traced port."""

import pytest
from opentelemetry.sdk.trace import TracerProvider

from app.adapters.outbound.tracing.openinference_tracer import OpenInferenceTracer
from app.application.tracing.null_tracer import NullTracer
from app.application.tracing.traced_chat_model import TracedChatModel
from app.application.tracing.traced_embedder import TracedEmbedder
from app.application.tracing.traced_reranker import TracedReranker
from app.application.tracing.traced_retriever import TracedRetriever
from app.bootstrap import infrastructure as infrastructure_module
from app.bootstrap.infrastructure import Infrastructure
from app.bootstrap.query_container import QueryContainer
from app.config.app_settings import AppSettings


class RecordingProvider(TracerProvider):
    def __init__(self) -> None:
        super().__init__()
        self.was_shut_down = False

    def shutdown(self) -> None:
        self.was_shut_down = True
        super().shutdown()


def _settings(**overrides: object) -> AppSettings:
    return AppSettings(_env_file=None, embedding_provider="ollama", **overrides)


def test_disabled_tracing_uses_the_null_tracer() -> None:
    assert isinstance(Infrastructure(_settings(tracing_enabled=False)).tracer, NullTracer)


async def test_enabled_tracing_exports_through_phoenix_and_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingProvider()
    monkeypatch.setattr(
        infrastructure_module, "create_phoenix_tracer_provider", lambda settings: provider
    )
    infrastructure = Infrastructure(_settings(tracing_enabled=True))

    assert isinstance(infrastructure.tracer, OpenInferenceTracer)
    await infrastructure.dispose()
    assert provider.was_shut_down


def test_query_ports_are_wrapped_in_tracing_decorators() -> None:
    settings = _settings(tracing_enabled=False, query_llm_provider="ollama")
    query = QueryContainer(Infrastructure(settings))

    assert isinstance(query.infrastructure.embedder, TracedEmbedder)
    assert isinstance(query.retriever, TracedRetriever)
    assert isinstance(query.reranker, TracedReranker)
    assert isinstance(query.chat_model, TracedChatModel)
