"""Candidate passage retrieval for a query."""

from abc import ABC, abstractmethod

from app.domain.retrieval.retrieved_match import RetrievedMatch


class Retriever(ABC):
    @abstractmethod
    async def retrieve(
        self, query_vector: list[float], query: str, latest_only: bool = True
    ) -> list[RetrievedMatch]:
        """``latest_only=False`` searches every version of each document."""
