"""Read the pipeline history of a document."""

from uuid import UUID

from app.application.errors import DocumentNotFoundError
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.domain.documents.pipeline import Pipeline


class ListDocumentPipelines:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, document_id: UUID) -> list[Pipeline]:
        async with self._uow_factory() as uow:
            if await uow.documents.get(document_id) is None:
                raise DocumentNotFoundError(f"Document {document_id} not found")
            return await uow.pipelines.list_for_document(document_id)
