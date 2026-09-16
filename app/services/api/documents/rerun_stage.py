"""Pipeline stage rerun operations."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.document import Document
from app.models.db.pipeline import Pipeline, PipelineStages, PipelineStatus
from app.models.api.document.rerun_pipeline import RerunPipeline
from app.services.api.documents.common import dispatch_pipeline, pipeline_stage_for


async def rerun_pipeline_from_stage(
    doc_id: str, stage: PipelineStages, session: AsyncSession
) -> RerunPipeline:
    document = await _find_document(doc_id, session)
    previous = await _latest_pipeline(document.id, session)
    pipeline = _new_rerun_pipeline(document, previous, stage)
    session.add(pipeline)

    document.status = PipelineStatus.IN_PROGRESS
    await session.commit()
    await dispatch_pipeline(document, pipeline, session, stage)
    return RerunPipeline(
        document_id=str(document.id),
        pipeline_id=str(pipeline.id),
        status=pipeline.status,
    )



async def _find_document(doc_id: str, session: AsyncSession) -> Document:
    try:
        document_id = UUID(doc_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    result = await session.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def _latest_pipeline(document_id: UUID, session: AsyncSession) -> Pipeline | None:
    result = await session.execute(
        select(Pipeline)
        .where(Pipeline.document_id == document_id)
        .order_by(Pipeline.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _new_rerun_pipeline(
    document: Document, previous: Pipeline | None, stage: PipelineStages
) -> Pipeline:
    now = datetime.now(UTC)
    chunking = stage is PipelineStages.CHUNKING
    last_uploaded, uploaded_at, parsed_at = _pipeline_timestamps(document, previous, now, chunking)
    return Pipeline(
        document_id=document.id,
        stage=pipeline_stage_for(stage),
        status=PipelineStatus.IN_PROGRESS,
        uploaded=True,
        last_uploaded=last_uploaded,
        parsed=chunking or bool(previous and previous.parsed),
        last_parsed=previous.last_parsed if previous else (now if chunking else None),
        chunked=bool(previous and previous.chunked),
        last_chunked=previous.last_chunked if previous else None,
        uploaded_at=uploaded_at,
        parsed_at=parsed_at,
    )


def _pipeline_timestamps(
    document: Document, previous: Pipeline | None, now: datetime, chunking: bool
) -> tuple[datetime, datetime, datetime | None]:
    last_uploaded = (
        previous.last_uploaded if previous and previous.last_uploaded else document.created_at
    )
    uploaded_at = previous.uploaded_at if previous and previous.uploaded_at else document.created_at
    parsed_at = previous.parsed_at if previous and previous.parsed_at else (now if chunking else None)
    return last_uploaded, uploaded_at, parsed_at
