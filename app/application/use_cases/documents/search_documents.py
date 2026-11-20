"""Hybrid search over indexed passages."""

from app.application.ports.embedder import Embedder
from app.application.ports.retriever import Retriever
from app.application.ports.tracer import Tracer
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.match_documents import match_documents
from app.application.tracing.null_tracer import NullTracer
from app.application.tracing.span_kind import SpanKind
from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.retrieval.retrieved_match import RetrievedMatch


class SearchDocuments:
    def __init__(
        self, embedder: Embedder, retriever: Retriever, tracer: Tracer | None = None
    ) -> None:
        self._embedder = embedder
        self._retriever = retriever
        self._tracer = tracer or NullTracer()

    async def execute(self, query: str, top_k: int) -> list[RetrievedMatch]:
        with self._tracer.span("documents.search", SpanKind.RETRIEVER) as span:
            span.set_input(query)
            span.set_top_k(top_k)
            vectors = await self._embedder.embed([query], EmbeddingTask.QUERY)
            matches = (await self._retriever.retrieve(vectors[0], query))[:top_k]
            span.set_documents(DocumentRole.RETRIEVED, match_documents(matches))
            return matches
