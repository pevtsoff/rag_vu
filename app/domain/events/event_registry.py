"""Maps event type names to classes and rebuilds events from envelopes."""

import types
from dataclasses import fields
from datetime import datetime
from typing import Any, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from app.domain.events.domain_event import ENVELOPE_FIELDS, DomainEvent
from app.domain.events.event_envelope import EventEnvelope
from app.domain.events.unknown_event_type_error import UnknownEventTypeError


class EventRegistry:
    def __init__(self, event_classes: list[type[DomainEvent]] | None = None) -> None:
        self._classes: dict[str, type[DomainEvent]] = {}
        for event_class in event_classes or []:
            self.register(event_class)

    def register(self, event_class: type[DomainEvent]) -> None:
        self._classes[event_class.event_type] = event_class

    def event_types(self) -> frozenset[str]:
        return frozenset(self._classes)

    def deserialize(self, envelope: EventEnvelope) -> DomainEvent:
        """Rebuild the concrete event, converting JSON payload values to field types."""
        event_class = self._classes.get(envelope.event_type)
        if event_class is None:
            raise UnknownEventTypeError(f"Unregistered event type: {envelope.event_type}")
        hints = get_type_hints(event_class)
        payload_fields = (item.name for item in fields(event_class))
        values = {
            name: _coerce(envelope.payload.get(name), hints[name])
            for name in payload_fields
            if name not in ENVELOPE_FIELDS
        }
        return event_class(
            event_id=envelope.event_id,
            producer=envelope.producer,
            occurred_at=envelope.occurred_at,
            **values,
        )


def _coerce(value: Any, hint: Any) -> Any:
    if value is None:
        return None
    target = _unwrap_optional(hint)
    if target is UUID and not isinstance(value, UUID):
        return UUID(str(value))
    if target is datetime and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _unwrap_optional(hint: Any) -> Any:
    if get_origin(hint) in (Union, types.UnionType):
        arguments = [argument for argument in get_args(hint) if argument is not type(None)]
        return arguments[0] if len(arguments) == 1 else hint
    return hint
