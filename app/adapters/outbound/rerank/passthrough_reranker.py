from app.application.ports.reranker import Reranker
from app.domain.retrieval.retrieved_match import RetrievedMatch


class PassthroughReranker(Reranker):
    """Keeps the retrieval order; used when no reranking provider is available."""

    def __init__(self, top_k: int) -> None:
        self._top_k = top_k

    async def rerank(self, query: str, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
        return matches[: self._top_k]
