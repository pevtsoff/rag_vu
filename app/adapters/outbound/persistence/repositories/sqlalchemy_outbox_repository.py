from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.models.outbox_event_model import OutboxEventModel
from app.adapters.outbound.persistence.models.outbox_status import OutboxStatus
from app.application.ports.outbox_repository import OutboxRepository
from app.domain.events.event_envelope import EventEnvelope


class SqlAlchemyOutboxRepository(OutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, envelopes: list[EventEnvelope]) -> None:
        if not envelopes:
            return
        self._session.add_all(_row(envelope) for envelope in envelopes)
        await self._session.flush()

    async def lock_pending(self, limit: int) -> list[EventEnvelope]:
        statement = (
            select(OutboxEventModel)
            .where(OutboxEventModel.status == OutboxStatus.PENDING.value)
            .order_by(OutboxEventModel.occurred_at, OutboxEventModel.event_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_envelope(row) for row in rows]

    async def mark_published(self, event_ids: list[UUID], at: datetime) -> None:
        if not event_ids:
            return
        statement = (
            update(OutboxEventModel)
            .where(OutboxEventModel.event_id.in_(event_ids))
            .values(status=OutboxStatus.PUBLISHED.value, published_at=at)
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(statement)


def _row(envelope: EventEnvelope) -> OutboxEventModel:
    return OutboxEventModel(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        producer=envelope.producer,
        occurred_at=envelope.occurred_at,
        aggregate_id=envelope.aggregate_id,
        payload=envelope.payload,
        status=OutboxStatus.PENDING.value,
    )


def _to_envelope(row: OutboxEventModel) -> EventEnvelope:
    return EventEnvelope(
        event_id=row.event_id,
        event_type=row.event_type,
        producer=row.producer,
        occurred_at=row.occurred_at,
        payload=dict(row.payload),
        aggregate_id=row.aggregate_id,
    )
