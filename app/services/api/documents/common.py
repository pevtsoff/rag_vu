"""Shared document service operations."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.document import Document
from app.models.db.pipeline import Pipeline, PipelineStages, PipelineStatus
from app.models.api.document import SearchRequest
from app.services.background_jobs.dispatch import enqueue_pipeline


async def get_document_record(doc_id: str, session: AsyncSession) -> Document:
    result = await session.execute(select(Document).where(Document.id == doc_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def search_documents(request: SearchRequest, session: AsyncSession) -> list[object]:
    return []


def pipeline_stage_for(stage: PipelineStages) -> PipelineStages:
    return stage


async def dispatch_pipeline(
    document: Document, pipeline: Pipeline, session: AsyncSession, stage: PipelineStages
) -> None:
    try:
        enqueue_pipeline(str(document.id), str(pipeline.id), from_stage=stage)
    except Exception as exc:
        pipeline.status = PipelineStatus.FAILED
        pipeline.error_stage = "dispatch"
        pipeline.error_message = f"Pipeline dispatch failed ({type(exc).__name__}): {exc}"
        document.status = PipelineStatus.FAILED
        await session.commit()
        raise HTTPException(status_code=503, detail=pipeline.error_message) from exc
