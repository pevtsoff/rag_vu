"""The inbox: one row per (event, consumer) pair, used to process each event once."""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.application.dto.inbox_delivery import InboxDelivery
from app.application.dto.inbox_message import InboxMessage
from app.domain.events.event_envelope import EventEnvelope


class InboxRepository(ABC):
    @abstractmethod
    async def receive(self, envelope: EventEnvelope, consumer: str, at: datetime) -> UUID | None:
        """Store the event for ``consumer``; return the new row id or None if already stored."""

    @abstractmethod
    async def mark_dispatched(self, inbox_ids: list[UUID], at: datetime) -> None: ...

    @abstractmethod
    async def claim(
        self, inbox_id: UUID, lock_token: UUID, now: datetime, locked_until: datetime
    ) -> InboxMessage | None:
        """Lock a received (or abandoned) message for processing; None if not claimable."""

    @abstractmethod
    async def complete(self, inbox_id: UUID, lock_token: UUID, at: datetime) -> bool:
        """Mark processed if the caller still holds the lock; return whether it did."""

    @abstractmethod
    async def fail(self, inbox_id: UUID, lock_token: UUID, error: str, at: datetime) -> None: ...

    @abstractmethod
    async def lock_redeliverable(
        self, now: datetime, dispatched_before: datetime, limit: int
    ) -> list[InboxDelivery]:
        """Stamp and return messages whose job was lost or abandoned."""
