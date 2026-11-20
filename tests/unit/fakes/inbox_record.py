from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.events.event_envelope import EventEnvelope


@dataclass
class InboxRecord:
    id: UUID
    consumer: str
    envelope: EventEnvelope
    received_at: datetime
    status: str = "RECEIVED"
    attempts: int = 0
    lock_token: UUID | None = None
    locked_until: datetime | None = None
    dispatched_at: datetime | None = None
    processed_at: datetime | None = None
    last_error: str | None = None
