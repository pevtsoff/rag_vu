"""Restart a document's pipeline from a chosen stage."""

from uuid import UUID

from app.application.errors import DocumentNotFoundError, NoActivePipelineError
from app.application.ports.tracer import Tracer
from app.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.tracing.null_tracer import NullTracer
from app.application.tracing.pipeline_run_recorder import PipelineRunRecorder
from app.application.use_cases.documents.stage_trigger_factory import (
    StageTriggerFactory,
)
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.event_envelope import EventEnvelope


class RerunPipeline:
    """Without ``force_run`` return the active pipeline; with it, replace that pipeline."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        triggers: StageTriggerFactory | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._triggers = triggers or StageTriggerFactory()
        self._runs = PipelineRunRecorder(tracer or NullTracer())

    async def execute(
        self, document_id: UUID, stage: PipelineStage, force_run: bool = False
    ) -> Pipeline:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id, for_update=True)
            if document is None:
                raise DocumentNotFoundError(f"Document {document_id} not found")
            active = await uow.pipelines.get_active(document.id, for_update=True)
            if not force_run:
                return _require_active(active)
            pipeline = await self._restart(uow, document, active, stage)
            await uow.commit()
        if active is not None:
            self._runs.record(active, document)
        return pipeline

    async def _restart(
        self, uow: UnitOfWork, document: Document, active: Pipeline | None, stage: PipelineStage
    ) -> Pipeline:
        previous = await uow.pipelines.get_latest(document.id)
        if active is not None:
            active.cancel()
            await uow.pipelines.update(active)
        pipeline = Pipeline.start(document.id, stage, previous)
        document.start_processing()
        await uow.documents.update(document)
        await uow.pipelines.add(pipeline)
        trigger = await self._triggers.build(uow, document, pipeline, stage)
        await uow.outbox.add([EventEnvelope.from_event(trigger)])
        return pipeline


def _require_active(active: Pipeline | None) -> Pipeline:
    if active is None:
        raise NoActivePipelineError("No pipeline is currently in progress")
    return active
