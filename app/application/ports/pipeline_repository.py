"""Persistence of pipeline runs."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.documents.pipeline import Pipeline


class PipelineRepository(ABC):
    @abstractmethod
    async def get(self, pipeline_id: UUID, for_update: bool = False) -> Pipeline | None: ...

    @abstractmethod
    async def get_active(self, document_id: UUID, for_update: bool = False) -> Pipeline | None:
        """Return the in-progress pipeline of a document, if any."""

    @abstractmethod
    async def get_latest(self, document_id: UUID) -> Pipeline | None: ...

    @abstractmethod
    async def list_for_document(self, document_id: UUID) -> list[Pipeline]:
        """Return all pipelines of a document, newest first."""

    @abstractmethod
    async def add(self, pipeline: Pipeline) -> None: ...

    @abstractmethod
    async def update(self, pipeline: Pipeline) -> None: ...
