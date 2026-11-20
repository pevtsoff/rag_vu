from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.models.inbox_event_model import (
    INBOX_UNIQUE_CONSTRAINT,
    InboxEventModel,
)
from app.adapters.outbound.persistence.models.inbox_status import InboxStatus
from app.application.dto.inbox_delivery import InboxDelivery
from app.application.dto.inbox_message import InboxMessage
from app.application.ports.inbox_repository import InboxRepository
from app.domain.events.event_envelope import EventEnvelope

_MESSAGE_COLUMNS = (
    InboxEventModel.id,
    InboxEventModel.consumer,
    InboxEventModel.event_id,
    InboxEventModel.event_type,
    InboxEventModel.producer,
    InboxEventModel.occurred_at,
    InboxEventModel.payload,
    InboxEventModel.aggregate_id,
    InboxEventModel.lock_token,
    InboxEventModel.attempts,
)


class SqlAlchemyInboxRepository(InboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def receive(self, envelope: EventEnvelope, consumer: str, at: datetime) -> UUID | None:
        statement = (
            insert(InboxEventModel)
            .values(_received_row(envelope, consumer, at))
            .on_conflict_do_nothing(constraint=INBOX_UNIQUE_CONSTRAINT)
            .returning(InboxEventModel.id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def mark_dispatched(self, inbox_ids: list[UUID], at: datetime) -> None:
        if inbox_ids:
            await self._update(InboxEventModel.id.in_(inbox_ids), dispatched_at=at)

    async def claim(
        self, inbox_id: UUID, lock_token: UUID, now: datetime, locked_until: datetime
    ) -> InboxMessage | None:
        claimable = or_(
            InboxEventModel.status == InboxStatus.RECEIVED.value,
            _abandoned(now),
        )
        statement = (
            update(InboxEventModel)
            .where(InboxEventModel.id == inbox_id, claimable)
            .values(
                status=InboxStatus.PROCESSING.value,
                lock_token=lock_token,
                locked_until=locked_until,
                attempts=InboxEventModel.attempts + 1,
            )
            .returning(*_MESSAGE_COLUMNS)
            .execution_options(synchronize_session=False)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return _to_message(row) if row is not None else None

    async def complete(self, inbox_id: UUID, lock_token: UUID, at: datetime) -> bool:
        statement = (
            update(InboxEventModel)
            .where(*_held_by(inbox_id, lock_token))
            .values(
                status=InboxStatus.PROCESSED.value,
                processed_at=at,
                locked_until=None,
                last_error=None,
            )
            .returning(InboxEventModel.id)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def fail(self, inbox_id: UUID, lock_token: UUID, error: str, at: datetime) -> None:
        await self._update(
            and_(*_held_by(inbox_id, lock_token)),
            status=InboxStatus.FAILED.value,
            last_error=error,
            processed_at=at,
            locked_until=None,
        )

    async def lock_redeliverable(
        self, now: datetime, dispatched_before: datetime, limit: int
    ) -> list[InboxDelivery]:
        last_dispatch = func.coalesce(InboxEventModel.dispatched_at, InboxEventModel.received_at)
        waiting = or_(InboxEventModel.status == InboxStatus.RECEIVED.value, _abandoned(now))
        statement = (
            select(InboxEventModel.id, InboxEventModel.consumer)
            .where(waiting, last_dispatch < dispatched_before)
            .order_by(InboxEventModel.received_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = (await self._session.execute(statement)).all()
        await self.mark_dispatched([row[0] for row in rows], now)
        return [InboxDelivery(inbox_id=row[0], consumer=row[1]) for row in rows]

    async def _update(self, condition: object, **values: object) -> None:
        statement = (
            update(InboxEventModel)
            .where(condition)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(statement)


def _abandoned(now: datetime) -> ColumnElement[bool]:
    return and_(
        InboxEventModel.status == InboxStatus.PROCESSING.value,
        InboxEventModel.locked_until < now,
    )


def _held_by(inbox_id: UUID, lock_token: UUID) -> tuple:
    return (
        InboxEventModel.id == inbox_id,
        InboxEventModel.lock_token == lock_token,
        InboxEventModel.status == InboxStatus.PROCESSING.value,
    )


def _received_row(envelope: EventEnvelope, consumer: str, at: datetime) -> dict:
    return {
        "id": uuid4(),
        "event_id": envelope.event_id,
        "consumer": consumer,
        "event_type": envelope.event_type,
        "producer": envelope.producer,
        "occurred_at": envelope.occurred_at,
        "aggregate_id": envelope.aggregate_id,
        "payload": envelope.payload,
        "status": InboxStatus.RECEIVED.value,
        "attempts": 0,
        "received_at": at,
    }


def _to_message(row: tuple) -> InboxMessage:
    envelope = EventEnvelope(
        event_id=row.event_id,
        event_type=row.event_type,
        producer=row.producer,
        occurred_at=row.occurred_at,
        payload=dict(row.payload),
        aggregate_id=row.aggregate_id,
    )
    return InboxMessage(
        id=row.id,
        consumer=row.consumer,
        envelope=envelope,
        lock_token=row.lock_token,
        attempts=row.attempts,
    )
