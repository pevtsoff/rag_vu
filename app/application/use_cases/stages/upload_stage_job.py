"""Stage 1: move the staged upload to permanent storage and verify it."""

from typing import Any

from app.application.dto.stored_file import StoredFile
from app.application.errors import StorageError
from app.application.ports.clock import Clock
from app.application.ports.file_storage import FileStorage
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.stages.stage_context import StageContext
from app.application.use_cases.stages.stage_job import StageJob
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.domain_event import DomainEvent
from app.domain.events.file_received_event import FileReceivedEvent
from app.domain.events.file_uploaded_event import FileUploadedEvent


class UploadStageJob(StageJob):
    consumer = "upload"
    stage = PipelineStage.UPLOADING

    def __init__(self, clock: Clock, storage: FileStorage) -> None:
        super().__init__(clock)
        self._storage = storage

    async def compute(self, context: StageContext) -> StoredFile:
        event = context.event
        if not isinstance(event, FileReceivedEvent):
            raise TypeError(f"{self.consumer} cannot handle {event.event_type}")
        stored = await self._storage.promote(event.staged_path, event.document_id, event.file_name)
        if stored.size != event.size or (event.sha256 and stored.sha256 != event.sha256):
            raise StorageError(f"Stored file {stored.path} does not match the uploaded content")
        return stored

    async def _store(
        self,
        uow: UnitOfWork,
        context: StageContext,
        document: Document,
        pipeline: Pipeline,
        result: Any,
    ) -> DomainEvent:
        document.relocate(result.path)
        return FileUploadedEvent(
            producer=self.consumer,
            document_id=document.id,
            pipeline_id=pipeline.id,
            file_path=result.path,
            file_name=document.file_name,
            size=result.size,
            sha256=result.sha256,
            mime_type=document.mime_type,
        )
