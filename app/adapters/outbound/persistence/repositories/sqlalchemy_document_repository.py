from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.flush import flush_or_conflict
from app.adapters.outbound.persistence.models.document_model import DocumentModel
from app.application.ports.document_repository import DocumentRepository
from app.domain.documents.document import Document
from app.domain.documents.pipeline_status import PipelineStatus

_COPIED_FIELDS = (
    "file_name",
    "file_path",
    "structure_path",
    "size",
    "mime_type",
    "sha256",
    "doc_metadata",
    "version",
)


class SqlAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, document_id: UUID, for_update: bool = False) -> Document | None:
        statement = select(DocumentModel).where(DocumentModel.id == document_id)
        return await self._one(statement, for_update)

    async def get_by_sha256(self, sha256: str, for_update: bool = False) -> Document | None:
        statement = select(DocumentModel).where(DocumentModel.sha256 == sha256)
        return await self._one(statement, for_update)

    async def add(self, document: Document) -> None:
        row = DocumentModel(id=document.id)
        _apply(document, row)
        self._session.add(row)
        await flush_or_conflict(self._session)

    async def update(self, document: Document) -> None:
        row = await self._session.get(DocumentModel, document.id)
        if row is None:
            raise LookupError(f"Document {document.id} is not stored")
        _apply(document, row)
        await flush_or_conflict(self._session)

    async def _one(self, statement: Select, for_update: bool) -> Document | None:
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None


def _apply(document: Document, row: DocumentModel) -> None:
    for name in _COPIED_FIELDS:
        setattr(row, name, getattr(document, name))
    row.status = str(document.status)


def _to_entity(row: DocumentModel) -> Document:
    return Document(
        id=row.id,
        status=PipelineStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        **{name: getattr(row, name) for name in _COPIED_FIELDS},
    )
