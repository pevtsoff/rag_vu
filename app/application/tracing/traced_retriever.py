from app.application.ports.retriever import Retriever
from app.application.ports.tracer import Tracer
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.match_documents import match_documents
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.trace_attributes import (
    RETRIEVAL_CANDIDATE_COUNT,
    RETRIEVAL_LATEST_ONLY,
    RETRIEVAL_SOURCE,
    RETRIEVAL_VECTOR_DIMENSIONS,
)
from app.domain.retrieval.retrieved_match import RetrievedMatch

HYBRID_SOURCE = "hybrid"


class TracedRetriever(Retriever):
    """Decorator: a RETRIEVER span holding the fused candidates handed to the reranker."""

    def __init__(self, inner: Retriever, tracer: Tracer) -> None:
        self._inner = inner
        self._tracer = tracer

    async def retrieve(
        self, query_vector: list[float], query: str, latest_only: bool = True
    ) -> list[RetrievedMatch]:
        with self._tracer.span("retrieval.hybrid", SpanKind.RETRIEVER) as span:
            span.set_input(query)
            span.set_attributes(
                {
                    RETRIEVAL_SOURCE: HYBRID_SOURCE,
                    RETRIEVAL_VECTOR_DIMENSIONS: len(query_vector),
                    RETRIEVAL_LATEST_ONLY: latest_only,
                }
            )
            matches = await self._inner.retrieve(query_vector, query, latest_only)
            span.set_attributes({RETRIEVAL_CANDIDATE_COUNT: len(matches)})
            span.set_documents(DocumentRole.RETRIEVED, match_documents(matches))
            return matches
