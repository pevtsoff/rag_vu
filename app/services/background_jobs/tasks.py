import asyncio
import traceback
from datetime import UTC, datetime
from uuid import UUID

from docling_core.types.doc import ImageRefMode
from sqlalchemy import delete, select
from sqlalchemy_utils.types.ltree import Ltree

from app.db.session import AsyncSessionLocal, engine
from app.models import Chunk, Document, Node
from app.models.db.pipeline import Pipeline, PipelineStages, PipelineStatus
from app.services.background_jobs.celery_app import celery_app
from app.services.background_jobs.exceptions import FileChunkingError, FileParsingError
from app.services.chunking import process_document_chunks
from app.services.parser.parser import build_nodes_from_docling, parse_document


def _error_details(stage_error: Exception) -> str:
    return f"{type(stage_error).__name__}: {stage_error}\n{traceback.format_exc()}"


def _run_async(coroutine):
    """Give each synchronous Celery task its own clean async DB pool lifecycle."""

    async def run_and_dispose():
        try:
            return await coroutine
        finally:
            await engine.dispose()

    return asyncio.run(run_and_dispose())


async def _mark_failure(document_id: str, pipeline_id: str, stage: str, exc: Exception):
    async with AsyncSessionLocal() as session:
        pipeline = await session.get(Pipeline, UUID(pipeline_id))
        document = await session.get(Document, UUID(document_id))
        if pipeline:
            pipeline.status = PipelineStatus.FAILED
            pipeline.error_stage = stage
            pipeline.error_message = _error_details(exc)
        if document:
            document.status = PipelineStatus.FAILED
        await session.commit()


@celery_app.task(name="ingestion.parse_document")
def parse_document_task(document_id: str, pipeline_id: str) -> str:
    try:
        _run_async(_parse_document(document_id, pipeline_id))
        return document_id
    except Exception as exc:
        error = exc if isinstance(exc, FileParsingError) else FileParsingError(str(exc))
        _run_async(_mark_failure(document_id, pipeline_id, "parsing", error))
        raise error from exc


async def _parse_document(document_id: str, pipeline_id: str) -> None:
    async with AsyncSessionLocal() as session:
        pipeline = await session.get(Pipeline, UUID(pipeline_id))
        document = await session.get(Document, UUID(document_id))

        if not pipeline or not document:
            raise FileParsingError("Pipeline or document record was not found")

        pipeline.status = PipelineStatus.IN_PROGRESS
        pipeline.error_message = None
        pipeline.error_stage = None
        await session.commit()

        try:
            title, docling_document = await asyncio.to_thread(parse_document, document.file_path)
            docling_path = f"{document.file_path}.docling.json"
            await asyncio.to_thread(
                docling_document.save_as_json,
                docling_path,
                image_mode=ImageRefMode.PLACEHOLDER,
            )
            # Replace the prior parse atomically; explicitly clear chunks as well
            # as nodes so stale embeddings cannot survive a re-upload/rerun.
            await session.execute(
                delete(Chunk).where(
                    Chunk.node_id.in_(select(Node.id).where(Node.document_id == document.id))
                )
            )

            await session.execute(delete(Node).where(Node.document_id == document.id))
            parsed_nodes = build_nodes_from_docling(docling_document, title or document.file_name)

            session.add_all(
                Node(
                    document_id=document.id,
                    title=parsed_node.title,
                    text=parsed_node.text,
                    node_type=parsed_node.node_type,
                    breadcrumbs=parsed_node.breadcrumbs,
                    path=Ltree(parsed_node.path),
                )
                for parsed_node in parsed_nodes
            )

            pipeline.stage = PipelineStages.CHUNKING
            pipeline.status = PipelineStatus.IN_PROGRESS
            pipeline.parsed_at = datetime.now(UTC)
            pipeline.parsed = True

            pipeline.last_parsed = pipeline.parsed_at
            document.status = PipelineStatus.IN_PROGRESS
            await session.commit()

        except Exception:
            await session.rollback()
            raise


@celery_app.task(name="ingestion.chunk_document")
def chunk_document_task(document_id: str, pipeline_id: str) -> str:
    try:
        _run_async(_chunk_document(document_id, pipeline_id))
        return document_id
    except Exception as exc:
        error = exc if isinstance(exc, FileChunkingError) else FileChunkingError(str(exc))
        _run_async(_mark_failure(document_id, pipeline_id, "chunking", error))
        raise error from exc


async def _chunk_document(document_id: str, pipeline_id: str) -> None:
    async with AsyncSessionLocal() as session:
        pipeline = await session.get(Pipeline, UUID(pipeline_id))
        document = await session.get(Document, UUID(document_id))

        if not pipeline or not document:
            raise FileChunkingError("Pipeline or document record was not found")

        pipeline.status = PipelineStatus.IN_PROGRESS
        pipeline.error_message = None
        pipeline.error_stage = None

        await session.commit()

        try:
            await process_document_chunks(
                session,
                document_id,
                docling_json_path=f"{document.file_path}.docling.json",
            )

            pipeline.stage = PipelineStages.CHUNKING
            pipeline.status = PipelineStatus.SUCCEEDED
            pipeline.chunked_at = datetime.now(UTC)
            pipeline.chunked = True

            pipeline.last_chunked = pipeline.chunked_at
            document.status = PipelineStatus.SUCCEEDED
            await session.commit()
        except Exception:
            await session.rollback()
            raise
