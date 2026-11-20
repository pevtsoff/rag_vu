"""Accept an uploaded file and start its ingestion pipeline."""

from app.application.dto.staged_file import StagedFile
from app.application.dto.upload_result import UploadResult
from app.application.errors import ConcurrencyConflictError
from app.application.ports.byte_stream import ByteStream
from app.application.ports.file_storage import FileStorage
from app.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.use_cases.documents.producers import API_PRODUCER
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.event_envelope import EventEnvelope
from app.domain.events.file_received_event import FileReceivedEvent


class UploadDocument:
    """Stage the file, deduplicate by SHA-256 and emit ``FileReceivedEvent``.

    The document, its pipeline and the event are committed in one transaction.
    """

    def __init__(self, uow_factory: UnitOfWorkFactory, storage: FileStorage) -> None:
        self._uow_factory = uow_factory
        self._storage = storage

    async def execute(
        self, stream: ByteStream, file_name: str, mime_type: str, force_run: bool = False
    ) -> UploadResult:
        staged = await self._storage.stage(stream, file_name, mime_type)
        try:
            result = await self._register(staged, force_run)
        except ConcurrencyConflictError:
            # A concurrent upload of the same content won the race; join it.
            result = await self._register(staged, force_run)
        if result.duplicate:
            await self._storage.discard(staged.path)
        return result

    async def _register(self, staged: StagedFile, force_run: bool) -> UploadResult:
        async with self._uow_factory() as uow:
            existing = await uow.documents.get_by_sha256(staged.sha256, for_update=True)
            if existing is None:
                result = await self._register_new(uow, staged)
            else:
                result = await self._register_duplicate(uow, existing, staged, force_run)
            await uow.commit()
        return result

    async def _register_new(self, uow: UnitOfWork, staged: StagedFile) -> UploadResult:
        document = Document(
            file_name=staged.file_name,
            file_path=staged.path,
            size=staged.size,
            sha256=staged.sha256,
            mime_type=staged.mime_type,
        )
        pipeline = Pipeline.start(document.id, PipelineStage.UPLOADING)
        await uow.documents.add(document)
        await uow.pipelines.add(pipeline)
        await uow.outbox.add([_file_received(document, pipeline, staged.path)])
        return UploadResult(document=document, pipeline=pipeline, duplicate=False)

    async def _register_duplicate(
        self, uow: UnitOfWork, document: Document, staged: StagedFile, force_run: bool
    ) -> UploadResult:
        active = await uow.pipelines.get_active(document.id, for_update=True)
        if active is not None and not force_run:
            return UploadResult(document=document, pipeline=active, duplicate=True)
        if active is not None:
            active.cancel()
            await uow.pipelines.update(active)
        pipeline = Pipeline.start(document.id, PipelineStage.UPLOADING)
        document.start_processing()
        await uow.documents.update(document)
        await uow.pipelines.add(pipeline)
        # The content is already stored; the upload stage only verifies it.
        await uow.outbox.add([_file_received(document, pipeline, document.file_path)])
        return UploadResult(document=document, pipeline=pipeline, duplicate=True)


def _file_received(document: Document, pipeline: Pipeline, staged_path: str) -> EventEnvelope:
    return EventEnvelope.from_event(
        FileReceivedEvent(
            producer=API_PRODUCER,
            document_id=document.id,
            pipeline_id=pipeline.id,
            staged_path=staged_path,
            file_name=document.file_name,
            size=document.size,
            sha256=document.sha256 or "",
            mime_type=document.mime_type,
        )
    )
