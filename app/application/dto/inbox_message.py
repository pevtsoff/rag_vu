from dataclasses import dataclass
from uuid import UUID

from app.domain.events.event_envelope import EventEnvelope


@dataclass(frozen=True)
class InboxMessage:
    id: UUID
    consumer: str
    envelope: EventEnvelope
    lock_token: UUID
    attempts: int
