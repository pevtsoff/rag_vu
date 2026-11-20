"""The stored, transport-neutral form of a domain event."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.events.domain_event import DomainEvent


@dataclass(frozen=True)
class EventEnvelope:
    event_id: UUID
    event_type: str
    producer: str
    occurred_at: datetime
    payload: dict[str, Any]
    aggregate_id: UUID | None = None

    @classmethod
    def from_event(cls, event: DomainEvent) -> "EventEnvelope":
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            producer=event.producer,
            occurred_at=event.occurred_at,
            payload=event.payload(),
            aggregate_id=event.aggregate_id,
        )
