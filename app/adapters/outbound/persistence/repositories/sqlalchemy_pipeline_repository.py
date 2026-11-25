from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.flush import flush_or_conflict
from app.adapters.outbound.persistence.models.pipeline_model import PipelineModel
from app.application.ports.pipeline_repository import PipelineRepository
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus

_COPIED_FIELDS = (
    "document_id",
    "uploaded",
    "parsed",
    "chunked",
    "embedded",
    "versioned",
    "uploaded_at",
    "parsed_at",
    "chunked_at",
    "embedded_at",
    "versioned_at",
    "error_message",
    "error_stage",
)


class SqlAlchemyPipelineRepository(PipelineRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, pipeline_id: UUID, for_update: bool = False) -> Pipeline | None:
        statement = select(PipelineModel).where(PipelineModel.id == pipeline_id)
        return await self._one(statement, for_update)

    async def get_active(self, document_id: UUID, for_update: bool = False) -> Pipeline | None:
        statement = select(PipelineModel).where(
            PipelineModel.document_id == document_id,
            PipelineModel.status == PipelineStatus.IN_PROGRESS.value,
        )
        return await self._one(statement, for_update)

    async def get_latest(self, document_id: UUID) -> Pipeline | None:
        statement = (
            select(PipelineModel)
            .where(PipelineModel.document_id == document_id)
            .order_by(PipelineModel.created_at.desc(), PipelineModel.id.desc())
            .limit(1)
        )
        return await self._one(statement, for_update=False)

    async def list_for_document(self, document_id: UUID) -> list[Pipeline]:
        statement = (
            select(PipelineModel)
            .where(PipelineModel.document_id == document_id)
            .order_by(PipelineModel.created_at.desc(), PipelineModel.id.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_entity(row) for row in rows]

    async def add(self, pipeline: Pipeline) -> None:
        row = PipelineModel(id=pipeline.id)
        _apply(pipeline, row)
        self._session.add(row)
        await flush_or_conflict(self._session)

    async def update(self, pipeline: Pipeline) -> None:
        row = await self._session.get(PipelineModel, pipeline.id)
        if row is None:
            raise LookupError(f"Pipeline {pipeline.id} is not stored")
        _apply(pipeline, row)
        await flush_or_conflict(self._session)

    async def _one(self, statement: Select, for_update: bool) -> Pipeline | None:
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None


def _apply(pipeline: Pipeline, row: PipelineModel) -> None:
    for name in _COPIED_FIELDS:
        setattr(row, name, getattr(pipeline, name))
    row.stage = str(pipeline.stage)
    row.status = str(pipeline.status)


def _to_entity(row: PipelineModel) -> Pipeline:
    return Pipeline(
        id=row.id,
        stage=PipelineStage(row.stage or PipelineStage.UPLOADING),
        status=PipelineStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        **{name: getattr(row, name) for name in _COPIED_FIELDS},
    )
