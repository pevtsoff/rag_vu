"""Document upload and initial pipeline operations."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.document import Document
from app.models.db.pipeline import Pipeline, PipelineStages, PipelineStatus
from app.models.api.document.upload_document import UploadDocument
from app.services.api.documents.common import dispatch_pipeline
from app.services.background_jobs.exceptions import FileUploadError
from app.settings import settings


async def upload_document(
    file: UploadFile, session: AsyncSession, force_run: bool = False
) -> UploadDocument:
    """Save an upload, create its pipeline, and dispatch processing."""
    filename = Path(file.filename or "upload").name
    upload_root = Path(settings.upload_path).resolve()
    temporary_path, sha256, size = await _stage_upload(file, upload_root)
    document, pipeline, duplicate, created = await _save_upload(
        file, session, filename, upload_root, temporary_path, sha256, size, force_run
    )
    if pipeline is not None and created:
        await dispatch_pipeline(document, pipeline, session, PipelineStages.PARSING)
    return UploadDocument(
        id=str(document.id),
        pipeline_id=str(pipeline.id) if pipeline is not None else None,
        filename=document.file_name,
        status=document.status,
        duplicate=duplicate,
    )


async def _stage_upload(file: UploadFile, upload_root: Path) -> tuple[Path, str, int]:
    incoming_dir = upload_root / ".incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = incoming_dir / f"{uuid4()}.upload"
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        error = exc if isinstance(exc, FileUploadError) else FileUploadError(f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=str(error)) from exc
    return temporary_path, digest.hexdigest(), size


async def _save_upload(
    file: UploadFile,
    session: AsyncSession,
    filename: str,
    upload_root: Path,
    temporary_path: Path,
    sha256: str,
    size: int,
    force_run: bool,
) -> tuple[Document, Pipeline | None, bool, bool]:
    result = await session.execute(
        select(Document).where(Document.sha256 == sha256).with_for_update()
    )
    document = result.scalar_one_or_none()
    if document:
        temporary_path.unlink(missing_ok=True)
        pipeline, created = await _existing_upload_pipeline(session, document, force_run)
        return document, pipeline, True, created
    return await _persist_new_upload(
        file, session, filename, upload_root, temporary_path, sha256, size, force_run
    )


async def _persist_new_upload(
    file: UploadFile,
    session: AsyncSession,
    filename: str,
    upload_root: Path,
    temporary_path: Path,
    sha256: str,
    size: int,
    force_run: bool,
) -> tuple[Document, Pipeline, bool, bool]:
    document_id = uuid4()
    path = upload_root / str(document_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.replace(path)
    document = _new_document(file, filename, path, sha256, size, document_id)
    session.add(document)
    pipeline = _new_upload_pipeline(document.id)
    session.add(pipeline)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        path.unlink(missing_ok=True)
        return await _recover_duplicate(session, sha256, exc, force_run)
    return document, pipeline, False, True


def _new_document(
    file: UploadFile, filename: str, path: Path, sha256: str, size: int, document_id: UUID
) -> Document:
    return Document(
        id=document_id,
        file_name=filename,
        file_path=str(path),
        sha256=sha256,
        size=size,
        mime_type=file.content_type or "application/octet-stream",
        status=PipelineStatus.IN_PROGRESS,
        version=1,
    )


async def _recover_duplicate(
    session: AsyncSession, sha256: str, conflict: IntegrityError, force_run: bool
) -> tuple[Document, Pipeline | None, bool, bool]:
    result = await session.execute(
        select(Document).where(Document.sha256 == sha256).with_for_update()
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise conflict
    pipeline, created = await _existing_upload_pipeline(session, document, force_run)
    return document, pipeline, True, created


async def _existing_upload_pipeline(
    session: AsyncSession, document: Document, force_run: bool
) -> tuple[Pipeline | None, bool]:
    active = await _active_pipeline(session, document)
    if active and not force_run:
        return active, False
    if active and force_run:
        active.status = PipelineStatus.CANCELLED
    pipeline = _new_upload_pipeline(document.id)
    document.status = PipelineStatus.IN_PROGRESS
    session.add(pipeline)
    await session.commit()
    return pipeline, True


async def _active_pipeline(session: AsyncSession, document: Document) -> Pipeline | None:
    result = await session.execute(
        select(Pipeline).where(
            Pipeline.document_id == document.id,
            Pipeline.status == PipelineStatus.IN_PROGRESS,
        )
    )
    return result.scalar_one_or_none()


def _new_upload_pipeline(document_id: UUID) -> Pipeline:
    now = datetime.now(UTC)
    return Pipeline(
        document_id=document_id,
        stage=PipelineStages.PARSING,
        status=PipelineStatus.IN_PROGRESS,
        uploaded=True,
        last_uploaded=now,
        uploaded_at=now,
    )
