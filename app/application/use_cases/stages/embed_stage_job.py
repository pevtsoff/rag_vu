"""Stage 4: embed every chunk of the document and finish the pipeline."""

from typing import Any
from uuid import UUID

from app.application.errors import EmptyStageResultError
from app.application.ports.clock import Clock
from app.application.ports.embedder import Embedder
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.stages.stage_context import StageContext
from app.application.use_cases.stages.stage_job import StageJob
from app.domain.documents.chunk import Chunk
from app.domain.documents.document import Document
from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.document_embedded_event import DocumentEmbeddedEvent
from app.domain.events.domain_event import DomainEvent


class EmbedStageJob(StageJob):
    consumer = "embedding"
    stage = PipelineStage.EMBEDDING

    def __init__(self, clock: Clock, embedder: Embedder, batch_size: int = 32) -> None:
        super().__init__(clock)
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._embedder = embedder
        self._batch_size = batch_size

    async def _load(self, uow: UnitOfWork, document: Document) -> list[Chunk]:
        chunks = await uow.chunks.list_for_document(document.id)
        if not chunks:
            raise EmptyStageResultError(f"No chunks to embed for document {document.id}")
        return chunks

    async def compute(self, context: StageContext) -> dict[UUID, list[float]]:
        chunks: list[Chunk] = context.data
        vectors: dict[UUID, list[float]] = {}
        for start in range(0, len(chunks), self._batch_size):
            batch = chunks[start : start + self._batch_size]
            embedded = await self._embedder.embed(
                [chunk.text for chunk in batch], EmbeddingTask.PASSAGE
            )
            vectors.update(zip((chunk.id for chunk in batch), embedded, strict=True))
        return vectors

    async def _store(
        self,
        uow: UnitOfWork,
        context: StageContext,
        document: Document,
        pipeline: Pipeline,
        result: Any,
    ) -> DomainEvent:
        await uow.chunks.store_embeddings(result, self._embedder.dimensions)
        return DocumentEmbeddedEvent(
            producer=self.consumer,
            document_id=document.id,
            pipeline_id=pipeline.id,
            chunk_count=len(result),
            dimensions=self._embedder.dimensions,
        )
