"""Builds the event that starts a pipeline at a given stage."""

from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.documents.producers import API_PRODUCER
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.document_chunked_event import DocumentChunkedEvent
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.file_received_event import FileReceivedEvent
from app.domain.events.file_uploaded_event import FileUploadedEvent
from app.domain.events.pipeline_event import PipelineEvent


class StageTriggerFactory:
    """Each stage is started by the event its predecessor would have emitted."""

    def __init__(self, producer: str = API_PRODUCER) -> None:
        self._producer = producer

    async def build(
        self, uow: UnitOfWork, document: Document, pipeline: Pipeline, stage: PipelineStage
    ) -> PipelineEvent:
        if stage is PipelineStage.UPLOADING:
            return self._file_event(FileReceivedEvent, document, pipeline, "staged_path")
        if stage is PipelineStage.PARSING:
            return self._file_event(FileUploadedEvent, document, pipeline, "file_path")
        if stage is PipelineStage.CHUNKING:
            return DocumentParsedEvent(
                **self._identity(document, pipeline),
                structure_path=document.structure_path,
                node_count=len(await uow.nodes.list_with_text(document.id)),
            )
        return DocumentChunkedEvent(
            **self._identity(document, pipeline),
            chunk_count=await uow.chunks.count_for_document(document.id),
        )

    def _file_event(
        self,
        event_class: type[FileReceivedEvent] | type[FileUploadedEvent],
        document: Document,
        pipeline: Pipeline,
        path_field: str,
    ) -> PipelineEvent:
        return event_class(
            **self._identity(document, pipeline),
            **{path_field: document.file_path},
            file_name=document.file_name,
            size=document.size,
            sha256=document.sha256 or "",
            mime_type=document.mime_type,
        )

    def _identity(self, document: Document, pipeline: Pipeline) -> dict:
        return {
            "producer": self._producer,
            "document_id": document.id,
            "pipeline_id": pipeline.id,
        }
