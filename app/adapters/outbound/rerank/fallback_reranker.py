import logging

import httpx

from app.application.ports.reranker import Reranker
from app.domain.retrieval.retrieved_match import RetrievedMatch

logger = logging.getLogger(__name__)
RECOVERABLE_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError, RuntimeError)


class FallbackReranker(Reranker):
    """Decorator: a failing reranker must not fail the answer; keep the hybrid order."""

    def __init__(self, inner: Reranker, top_k: int) -> None:
        self._inner = inner
        self._top_k = top_k

    async def rerank(self, query: str, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
        if not matches:
            return []
        try:
            return await self._inner.rerank(query, matches)
        except RECOVERABLE_ERRORS as exc:
            logger.warning("Reranking failed (%s); using hybrid retrieval order.", exc)
            return matches[: self._top_k]
