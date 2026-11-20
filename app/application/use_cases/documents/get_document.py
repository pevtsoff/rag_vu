"""Read one document."""

from uuid import UUID

from app.application.errors import DocumentNotFoundError
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.domain.documents.document import Document


class GetDocument:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, document_id: UUID) -> Document:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        return document
