"""The transactional outbox: events written with the state change that caused them."""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.events.event_envelope import EventEnvelope


class OutboxRepository(ABC):
    @abstractmethod
    async def add(self, envelopes: list[EventEnvelope]) -> None: ...

    @abstractmethod
    async def lock_pending(self, limit: int) -> list[EventEnvelope]:
        """Lock up to ``limit`` unpublished events, oldest first, skipping locked rows."""

    @abstractmethod
    async def mark_published(self, event_ids: list[UUID], at: datetime) -> None: ...
