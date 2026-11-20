"""Splitting of document nodes into embeddable chunks."""

from abc import ABC, abstractmethod

from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.node import Node


class Chunker(ABC):
    @abstractmethod
    async def chunk(self, nodes: list[Node], structure_path: str | None) -> list[ChunkDraft]:
        """Chunk the nodes, using the parser's structure file when it is available."""
