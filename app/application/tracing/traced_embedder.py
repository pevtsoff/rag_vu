from app.application.ports.embedder import Embedder
from app.application.ports.trace_span import TraceSpan
from app.application.ports.tracer import Tracer
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.trace_attributes import (
    EMBEDDING_COUNT,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_TASK,
    EMBEDDING_TEXT_CHARS,
    EMBEDDING_TEXT_COUNT,
)
from app.domain.documents.embedding_task import EmbeddingTask


class TracedEmbedder(Embedder):
    """Decorator: one EMBEDDING span per provider call (a query or a passage batch)."""

    def __init__(self, inner: Embedder, tracer: Tracer, model_name: str) -> None:
        self._inner = inner
        self._tracer = tracer
        self._model_name = model_name

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    async def embed(self, texts: list[str], task: EmbeddingTask) -> list[list[float]]:
        with self._tracer.span(f"embedding.{task}", SpanKind.EMBEDDING) as span:
            self._describe_request(span, texts, task)
            vectors = await self._inner.embed(texts, task)
            span.set_attributes(
                {
                    EMBEDDING_COUNT: len(vectors),
                    EMBEDDING_DIMENSIONS: len(vectors[0]) if vectors else 0,
                }
            )
            return vectors

    def _describe_request(self, span: TraceSpan, texts: list[str], task: EmbeddingTask) -> None:
        span.set_model(self._model_name)
        span.set_attributes(
            {
                EMBEDDING_TASK: str(task),
                EMBEDDING_TEXT_COUNT: len(texts),
                EMBEDDING_TEXT_CHARS: sum(len(text) for text in texts),
            }
        )
        if task is EmbeddingTask.QUERY and len(texts) == 1:
            span.set_input(texts[0])
