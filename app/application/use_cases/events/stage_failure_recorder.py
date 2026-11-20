"""Records a failed stage: inbox message, pipeline, document and a failure event."""

from app.application.dto.inbox_message import InboxMessage
from app.application.ports.clock import Clock
from app.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.event_envelope import EventEnvelope
from app.domain.events.pipeline_event import PipelineEvent
from app.domain.events.pipeline_failed_event import PipelineFailedEvent

MAX_ERROR_LENGTH = 10_000


class StageFailureRecorder:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def record(
        self,
        message: InboxMessage,
        event: PipelineEvent | None,
        stage: PipelineStage,
        error: str,
    ) -> None:
        """Mark the message failed and, when the event is known, fail its pipeline."""
        error = error[:MAX_ERROR_LENGTH]
        async with self._uow_factory() as uow:
            await uow.inbox.fail(message.id, message.lock_token, error, self._clock.now())
            if event is not None:
                await self._fail_pipeline(uow, event, stage, error, message.consumer)
            await uow.commit()

    async def _fail_pipeline(
        self, uow: UnitOfWork, event: PipelineEvent, stage: PipelineStage, error: str, producer: str
    ) -> None:
        pipeline = await uow.pipelines.get(event.pipeline_id, for_update=True)
        if pipeline is None or not pipeline.is_active:
            return
        pipeline.fail(stage, error)
        await uow.pipelines.update(pipeline)
        document = await uow.documents.get(event.document_id, for_update=True)
        if document is not None:
            document.fail()
            await uow.documents.update(document)
        failed = PipelineFailedEvent(
            producer=producer,
            document_id=event.document_id,
            pipeline_id=event.pipeline_id,
            stage=str(stage),
            error=error,
        )
        await uow.outbox.add([EventEnvelope.from_event(failed)])
