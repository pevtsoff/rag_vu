"""Persistence of documents."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.documents.document import Document


class DocumentRepository(ABC):
    @abstractmethod
    async def get(self, document_id: UUID, for_update: bool = False) -> Document | None: ...

    @abstractmethod
    async def get_by_sha256(self, sha256: str, for_update: bool = False) -> Document | None: ...

    @abstractmethod
    async def add(self, document: Document) -> None: ...

    @abstractmethod
    async def update(self, document: Document) -> None: ...
