"""Stage 3: split the parsed nodes into chunks (without vectors)."""

from typing import Any

from app.application.errors import EmptyStageResultError
from app.application.ports.chunker import Chunker
from app.application.ports.clock import Clock
from app.application.ports.trace_span import TraceValue
from app.application.ports.unit_of_work import UnitOfWork
from app.application.tracing.trace_attributes import (
    CHUNK_AVG_CHARS,
    CHUNK_COUNT,
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    CHUNK_SOURCE_NODES,
)
from app.application.use_cases.stages.stage_context import StageContext
from app.application.use_cases.stages.stage_job import StageJob
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.document import Document
from app.domain.documents.node import Node
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.document_chunked_event import DocumentChunkedEvent
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.domain_event import DomainEvent


class ChunkStageJob(StageJob):
    consumer = "chunking"
    stage = PipelineStage.CHUNKING

    def __init__(self, clock: Clock, chunker: Chunker) -> None:
        super().__init__(clock)
        self._chunker = chunker

    async def _load(self, uow: UnitOfWork, document: Document) -> list[Node]:
        nodes = await uow.nodes.list_with_text(document.id)
        if not nodes:
            raise EmptyStageResultError(f"No parsed text nodes found for document {document.id}")
        return nodes

    async def compute(self, context: StageContext) -> list[ChunkDraft]:
        event = context.event
        structure_path = event.structure_path if isinstance(event, DocumentParsedEvent) else None
        chunks = await self._chunker.chunk(context.data, structure_path)
        if not chunks:
            raise EmptyStageResultError(
                f"No text chunks could be created for document {context.document.id}"
            )
        return chunks

    def trace_attributes(self, context: StageContext, result: Any) -> dict[str, TraceValue]:
        lengths = [len(chunk.text) for chunk in result] or [0]
        return {
            CHUNK_SOURCE_NODES: len(context.data or []),
            CHUNK_COUNT: len(result),
            CHUNK_AVG_CHARS: round(sum(lengths) / len(lengths), 1),
            CHUNK_MIN_CHARS: min(lengths),
            CHUNK_MAX_CHARS: max(lengths),
        }

    async def _store(
        self,
        uow: UnitOfWork,
        context: StageContext,
        document: Document,
        pipeline: Pipeline,
        result: Any,
    ) -> DomainEvent:
        chunk_count = await uow.chunks.replace_for_document(document.id, result)
        return DocumentChunkedEvent(
            producer=self.consumer,
            document_id=document.id,
            pipeline_id=pipeline.id,
            chunk_count=chunk_count,
        )
