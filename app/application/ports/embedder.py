"""Text embedding provider."""

from abc import ABC, abstractmethod

from app.domain.documents.embedding_task import EmbeddingTask


class Embedder(ABC):
    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Length of every vector this embedder returns."""

    @abstractmethod
    async def embed(self, texts: list[str], task: EmbeddingTask) -> list[list[float]]: ...
