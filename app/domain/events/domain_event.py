"""Base class of every domain event."""

from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID, uuid4

ENVELOPE_FIELDS = frozenset({"event_id", "producer", "occurred_at"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """An immutable fact. ``event_type`` is the class name of the concrete event."""

    event_type: ClassVar[str] = "DomainEvent"

    producer: str
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utc_now)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.event_type = cls.__name__

    @property
    def aggregate_id(self) -> UUID | None:
        return None

    def payload(self) -> dict[str, Any]:
        """Return the event-specific fields as JSON-compatible values."""
        return {
            item.name: _to_json(getattr(self, item.name))
            for item in fields(self)
            if item.name not in ENVELOPE_FIELDS
        }


def _to_json(value: Any) -> Any:
    if isinstance(value, (UUID, Path)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
