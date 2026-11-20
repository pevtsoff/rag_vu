"""Hybrid search over indexed passages."""

from app.application.ports.embedder import Embedder
from app.application.ports.retriever import Retriever
from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.retrieval.retrieved_match import RetrievedMatch


class SearchDocuments:
    def __init__(self, embedder: Embedder, retriever: Retriever) -> None:
        self._embedder = embedder
        self._retriever = retriever

    async def execute(self, query: str, top_k: int) -> list[RetrievedMatch]:
        vectors = await self._embedder.embed([query], EmbeddingTask.QUERY)
        matches = await self._retriever.retrieve(vectors[0], query)
        return matches[:top_k]
