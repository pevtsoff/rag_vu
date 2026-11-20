from app.application.ports.reranker import Reranker
from app.application.ports.tracer import Tracer
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.match_documents import match_documents
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.trace_attributes import RERANK_ORDER_CHANGED
from app.domain.retrieval.retrieved_match import RetrievedMatch


class TracedReranker(Reranker):
    """Decorator: a RERANKER span with the candidates before and after reranking."""

    def __init__(self, inner: Reranker, tracer: Tracer, model_name: str, top_k: int) -> None:
        self._inner = inner
        self._tracer = tracer
        self._model_name = model_name
        self._top_k = top_k

    async def rerank(self, query: str, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
        with self._tracer.span("rerank", SpanKind.RERANKER) as span:
            span.set_input(query)
            span.set_model(self._model_name)
            span.set_top_k(self._top_k)
            span.set_documents(DocumentRole.RERANK_INPUT, match_documents(matches))
            reranked = await self._inner.rerank(query, matches)
            span.set_documents(DocumentRole.RERANK_OUTPUT, match_documents(reranked))
            span.set_attributes({RERANK_ORDER_CHANGED: _order_changed(matches, reranked)})
            return reranked


def _order_changed(before: list[RetrievedMatch], after: list[RetrievedMatch]) -> bool:
    """False when reranking kept the hybrid order (e.g. a fallback or passthrough)."""
    return [match.node_ids for match in before[: len(after)]] != [match.node_ids for match in after]
