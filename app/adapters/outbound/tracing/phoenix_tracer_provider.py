"""OpenTelemetry tracer provider that exports spans to Arize Phoenix."""

from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from phoenix.otel import register

from app.config.app_settings import AppSettings


def create_phoenix_tracer_provider(settings: AppSettings) -> TracerProvider:
    """Create the provider in the process that will use it.

    The batch exporter runs a background thread, which does not survive a fork, so Celery
    workers must build it lazily inside the child process (see ``Infrastructure.tracer``).
    """
    provider = register(
        endpoint=settings.phoenix_collector_endpoint,
        project_name=settings.phoenix_project_name,
        batch=True,
        set_global_tracer_provider=False,
        verbose=False,
    )
    # Every provider call (embeddings, rerank, chat) becomes a child HTTP span with latency
    # and status code; request headers such as API keys are not recorded.
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    return provider
