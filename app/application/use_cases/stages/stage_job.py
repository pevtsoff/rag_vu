"""Template for a pipeline stage that consumes one event and emits the next."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.application.dto.persisted_stage import PersistedStage
from app.application.ports.clock import Clock
from app.application.ports.trace_span import TraceValue
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.stages.stage_context import StageContext
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.domain_event import DomainEvent
from app.domain.events.pipeline_event import PipelineEvent


class StageJob(ABC):
    """Splits a stage into a short read, slow work outside a transaction, and a short write.

    ``prepare`` and ``persist`` return None/[] when the pipeline is no longer active, which
    means a newer run replaced it and this message must be acknowledged without effect.
    """

    consumer: ClassVar[str]
    stage: ClassVar[PipelineStage]

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def prepare(self, uow: UnitOfWork, event: PipelineEvent) -> StageContext | None:
        found = await self._active_pipeline(uow, event, for_update=False)
        if found is None:
            return None
        _, document = found
        return StageContext(event=event, document=document, data=await self._load(uow, document))

    @abstractmethod
    async def compute(self, context: StageContext) -> Any:
        """Do the slow work; must not touch the database."""

    async def persist(self, uow: UnitOfWork, context: StageContext, result: Any) -> PersistedStage:
        found = await self._active_pipeline(uow, context.event, for_update=True)
        if found is None:
            return PersistedStage()
        pipeline, document = found
        next_event = await self._store(uow, context, document, pipeline, result)
        await self._advance(uow, pipeline, document)
        finished = None if pipeline.is_active else pipeline
        return PersistedStage([next_event], finished_pipeline=finished, document=document)

    def trace_attributes(self, context: StageContext, result: Any) -> dict[str, TraceValue]:
        """Describe the ``compute`` result on the stage's trace span; override per stage."""
        return {}

    async def _load(self, uow: UnitOfWork, document: Document) -> Any:
        """Load extra data for ``compute``; override when a stage needs it."""
        return None

    @abstractmethod
    async def _store(
        self,
        uow: UnitOfWork,
        context: StageContext,
        document: Document,
        pipeline: Pipeline,
        result: Any,
    ) -> DomainEvent:
        """Write the stage result and return the event announcing it."""

    async def _active_pipeline(
        self, uow: UnitOfWork, event: PipelineEvent, for_update: bool
    ) -> tuple[Pipeline, Document] | None:
        pipeline = await uow.pipelines.get(event.pipeline_id, for_update=for_update)
        if pipeline is None or not pipeline.is_active or pipeline.stage is not self.stage:
            return None
        document = await uow.documents.get(event.document_id, for_update=for_update)
        return (pipeline, document) if document is not None else None

    async def _advance(self, uow: UnitOfWork, pipeline: Pipeline, document: Document) -> None:
        pipeline.complete(self.stage, self._clock.now())
        if not pipeline.is_active:
            document.succeed()
        await uow.pipelines.update(pipeline)
        await uow.documents.update(document)
