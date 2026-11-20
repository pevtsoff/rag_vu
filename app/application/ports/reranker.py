"""Reordering of retrieved candidates by relevance."""

from abc import ABC, abstractmethod

from app.domain.retrieval.retrieved_match import RetrievedMatch


class Reranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, matches: list[RetrievedMatch]) -> list[RetrievedMatch]: ...
