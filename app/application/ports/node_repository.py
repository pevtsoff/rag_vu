"""Persistence of structural document nodes."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.documents.node import Node
from app.domain.documents.parsed_node import ParsedNode


class NodeRepository(ABC):
    @abstractmethod
    async def replace_for_document(self, document_id: UUID, nodes: list[ParsedNode]) -> int:
        """Delete a document's nodes and chunks, store ``nodes``, and return their count."""

    @abstractmethod
    async def list_with_text(self, document_id: UUID) -> list[Node]:
        """Return the document's nodes that have text, ordered by path."""

    @abstractmethod
    async def get_with_document_title(self, node_id: UUID) -> tuple[Node, str] | None: ...
