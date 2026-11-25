from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.flush import flush_or_conflict
from app.adapters.outbound.persistence.models.document_model import DocumentModel
from app.application.ports.document_repository import DocumentRepository
from app.domain.documents.document import IDENTIFIER_KEY, Document
from app.domain.documents.pipeline_status import PipelineStatus
from app.domain.versioning.document_fingerprint import DocumentFingerprint
from app.domain.versioning.fingerprint_candidate import FingerprintCandidate

_COPIED_FIELDS = (
    "file_name",
    "file_path",
    "structure_path",
    "size",
    "mime_type",
    "sha256",
    "doc_metadata",
    "version",
    "cluster_id",
    "is_latest",
)
LIVE = DocumentModel.deleted_at.is_(None)
LATEST = (DocumentModel.is_latest.is_(True), LIVE)


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

    async def latest_with_file_name(
        self, file_name: str, for_update: bool = False
    ) -> list[Document]:
        statement = (
            select(DocumentModel)
            .where(DocumentModel.file_name == file_name, *LATEST)
            .order_by(DocumentModel.created_at)
        )
        if for_update:
            statement = statement.with_for_update()
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_entity(row) for row in rows]

    async def exists_with_file_name(self, file_name: str) -> bool:
        statement = select(DocumentModel.id).where(DocumentModel.file_name == file_name, LIVE)
        return (await self._session.execute(statement.limit(1))).first() is not None

    async def latest_in_cluster(
        self, cluster_id: UUID, for_update: bool = False
    ) -> Document | None:
        statement = select(DocumentModel).where(DocumentModel.cluster_id == cluster_id, *LATEST)
        return await self._one(statement, for_update)

    async def highest_other_version(self, cluster_id: UUID, exclude_id: UUID) -> Document | None:
        statement = (
            select(DocumentModel)
            .where(DocumentModel.cluster_id == cluster_id, DocumentModel.id != exclude_id, LIVE)
            .order_by(DocumentModel.version.desc())
            .limit(1)
        )
        return await self._one(statement, for_update=True)

    async def max_version(self, cluster_id: UUID) -> int:
        statement = select(func.coalesce(func.max(DocumentModel.version), 0)).where(
            DocumentModel.cluster_id == cluster_id, LIVE
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def store_fingerprint(self, document_id: UUID, fingerprint: DocumentFingerprint) -> None:
        await self._session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == document_id)
            .values(avg_embedding=fingerprint.avg_embedding, minhash_sig=list(fingerprint.minhash))
        )

    async def latest_with_identifier(
        self, identifier: str, exclude_cluster_id: UUID, vector: list[float] | None
    ) -> FingerprintCandidate | None:
        statement = (
            _candidate_columns(vector)
            .where(
                *LATEST,
                DocumentModel.cluster_id != exclude_cluster_id,
                DocumentModel.doc_metadata[IDENTIFIER_KEY].astext == identifier,
            )
            .order_by(DocumentModel.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(statement)).first()
        return _candidate(row) if row is not None else None

    async def nearest_latest(
        self, vector: list[float], max_distance: float, limit: int, exclude_cluster_id: UUID
    ) -> list[FingerprintCandidate]:
        distance = DocumentModel.avg_embedding.cosine_distance(vector)
        statement = (
            _candidate_columns(vector)
            .where(
                *LATEST,
                DocumentModel.cluster_id != exclude_cluster_id,
                DocumentModel.avg_embedding.is_not(None),
                distance <= max_distance,
            )
            .order_by(distance)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [_candidate(row) for row in rows]

    async def _one(self, statement: Select, for_update: bool) -> Document | None:
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None


def _candidate_columns(vector: list[float] | None) -> Select:
    if vector is None:
        distance: Any = None
    else:
        distance = DocumentModel.avg_embedding.cosine_distance(vector)
    return select(
        DocumentModel.id,
        DocumentModel.cluster_id,
        DocumentModel.version,
        distance,
        DocumentModel.minhash_sig,
        DocumentModel.doc_metadata[IDENTIFIER_KEY].astext,
    )


def _candidate(row: Any) -> FingerprintCandidate:
    document_id, cluster_id, version, distance, minhash, identifier = row
    return FingerprintCandidate(
        document_id=document_id,
        cluster_id=cluster_id,
        version=version,
        # pgvector cosine distance is 0..2; map it to a 0..1 similarity.
        semantic_similarity=None if distance is None else 1.0 - float(distance) / 2.0,
        minhash=tuple(minhash) if minhash else None,
        identifier=identifier,
    )


def _apply(document: Document, row: DocumentModel) -> None:
    for name in _COPIED_FIELDS:
        setattr(row, name, getattr(document, name))
    row.status = str(document.status)
    # deleted_at is TIMESTAMP WITHOUT TIME ZONE (shared TimestampedModel): store naive UTC.
    deleted_at = document.deleted_at
    row.deleted_at = deleted_at.astimezone(UTC).replace(tzinfo=None) if deleted_at else None


def _to_entity(row: DocumentModel) -> Document:
    return Document(
        id=row.id,
        status=PipelineStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=_aware(row.deleted_at),
        **{name: getattr(row, name) for name in _COPIED_FIELDS},
    )


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value
