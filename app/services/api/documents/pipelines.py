"""Read pipeline history for documents."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.document import Document
from app.models.db.pipeline import Pipeline


async def get_document_pipelines(doc_id: str, session: AsyncSession) -> list[Pipeline]:
    document_result = await session.execute(select(Document).where(Document.id == doc_id))
    if document_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Document not found")

    pipeline_result = await session.execute(
        select(Pipeline)
        .where(Pipeline.document_id == doc_id)
        .order_by(Pipeline.created_at.desc())
    )
    return list(pipeline_result.scalars().all())
