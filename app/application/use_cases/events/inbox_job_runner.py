"""Runs a stage job for one inbox message, exactly once per (event, consumer)."""

import logging
import traceback
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from app.application.dto.inbox_message import InboxMessage
from app.application.dto.job_outcome import JobOutcome
from app.application.errors import ConcurrencyConflictError, StageJobError
from app.application.ports.clock import Clock
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.events.stage_failure_recorder import StageFailureRecorder
from app.application.use_cases.stages.stage_context import StageContext
from app.application.use_cases.stages.stage_job import StageJob
from app.domain.events.event_envelope import EventEnvelope
from app.domain.events.event_registry import EventRegistry
from app.domain.events.pipeline_event import PipelineEvent

logger = logging.getLogger(__name__)


class InboxJobRunner:
    """Claim → prepare → compute → persist (+ next event + ack) in one transaction.

    Idempotency: only a claimed message is processed, and the acknowledgement commits
    atomically with the stage result, so redelivered or duplicated jobs do nothing.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        registry: EventRegistry,
        job: StageJob,
        clock: Clock,
        lock_timeout: timedelta,
    ) -> None:
        self._uow_factory = uow_factory
        self._registry = registry
        self._job = job
        self._clock = clock
        self._lock_timeout = lock_timeout
        self._failures = StageFailureRecorder(uow_factory, clock)

    @property
    def consumer(self) -> str:
        return self._job.consumer

    async def run(self, inbox_id: UUID) -> JobOutcome:
        message = await self._claim(inbox_id)
        if message is None:
            logger.info("Inbox message %s is already handled or locked", inbox_id)
            return JobOutcome.ALREADY_HANDLED
        try:
            event = self._event(message)
        except Exception as exc:
            await self._failures.record(message, None, self._job.stage, _details(exc))
            raise StageJobError(f"{self.consumer} cannot read inbox {inbox_id}: {exc}") from exc
        return await self._run_claimed(message, event)

    async def _run_claimed(self, message: InboxMessage, event: PipelineEvent) -> JobOutcome:
        try:
            return await self._process(message, event)
        except ConcurrencyConflictError:
            # Another worker reclaimed the message after our lock expired; it owns it now.
            logger.warning("Lost the lock on inbox message %s; leaving it", message.id)
            return JobOutcome.ALREADY_HANDLED
        except Exception as exc:
            await self._failures.record(message, event, self._job.stage, _details(exc))
            raise StageJobError(f"{self.consumer} failed for inbox {message.id}: {exc}") from exc

    async def _claim(self, inbox_id: UUID) -> InboxMessage | None:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            message = await uow.inbox.claim(inbox_id, uuid4(), now, now + self._lock_timeout)
            await uow.commit()
        return message

    def _event(self, message: InboxMessage) -> PipelineEvent:
        event = self._registry.deserialize(message.envelope)
        if not isinstance(event, PipelineEvent):
            raise TypeError(f"{self.consumer} cannot handle {message.envelope.event_type}")
        return event

    async def _process(self, message: InboxMessage, event: PipelineEvent) -> JobOutcome:
        async with self._uow_factory() as uow:
            context = await self._job.prepare(uow, event)
        if context is None:
            await self._acknowledge(message, None, None)
            return JobOutcome.SKIPPED
        result = await self._job.compute(context)
        return await self._acknowledge(message, context, result)

    async def _acknowledge(
        self, message: InboxMessage, context: StageContext | None, result: Any
    ) -> JobOutcome:
        async with self._uow_factory() as uow:
            events = [] if context is None else await self._job.persist(uow, context, result)
            await uow.outbox.add([EventEnvelope.from_event(event) for event in events])
            if not await uow.inbox.complete(message.id, message.lock_token, self._clock.now()):
                raise ConcurrencyConflictError(f"Lost the lock on inbox message {message.id}")
            await uow.commit()
        return JobOutcome.PROCESSED if events else JobOutcome.SKIPPED


def _details(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
