"""Persistence of chunks and their vectors."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.documents.chunk import Chunk
from app.domain.documents.chunk_draft import ChunkDraft


class ChunkRepository(ABC):
    @abstractmethod
    async def replace_for_document(self, document_id: UUID, chunks: list[ChunkDraft]) -> int:
        """Delete a document's chunks, store ``chunks`` without vectors, return the count."""

    @abstractmethod
    async def list_for_document(self, document_id: UUID) -> list[Chunk]: ...

    @abstractmethod
    async def count_for_document(self, document_id: UUID) -> int: ...

    @abstractmethod
    async def store_embeddings(self, vectors: dict[UUID, list[float]], dimensions: int) -> None:
        """Store each chunk's vector in the column matching ``dimensions``."""
