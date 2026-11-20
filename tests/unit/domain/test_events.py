from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.events.default_event_registry import default_event_registry
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.event_envelope import EventEnvelope
from app.domain.events.event_registry import EventRegistry
from app.domain.events.file_uploaded_event import FileUploadedEvent
from app.domain.events.unknown_event_type_error import UnknownEventTypeError


def _uploaded() -> FileUploadedEvent:
    return FileUploadedEvent(
        producer="upload",
        document_id=uuid4(),
        pipeline_id=uuid4(),
        file_path="/media/documents/x/law.pdf",
        file_name="law.pdf",
        size=10,
        sha256="abc",
        mime_type="application/pdf",
    )


def test_every_event_has_the_required_envelope_fields() -> None:
    event = _uploaded()
    assert isinstance(event.event_id, UUID)
    assert event.event_type == "FileUploadedEvent"
    assert event.producer == "upload"
    assert event.occurred_at.tzinfo is not None


def test_events_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        _uploaded().size = 1  # type: ignore[misc]


def test_envelope_payload_is_json_compatible_and_excludes_envelope_fields() -> None:
    event = _uploaded()
    envelope = EventEnvelope.from_event(event)
    assert envelope.aggregate_id == event.document_id
    assert envelope.payload["document_id"] == str(event.document_id)
    assert envelope.payload["size"] == 10
    assert not {"event_id", "producer", "occurred_at"} & envelope.payload.keys()


def test_registry_round_trips_events_with_typed_fields() -> None:
    event = DocumentParsedEvent(
        producer="parsing",
        document_id=uuid4(),
        pipeline_id=uuid4(),
        structure_path=None,
        node_count=3,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    restored = default_event_registry().deserialize(EventEnvelope.from_event(event))
    assert restored == event
    assert isinstance(restored.document_id, UUID)


def test_unknown_event_type_is_rejected() -> None:
    envelope = EventEnvelope(uuid4(), "Nope", "test", datetime.now(UTC), {})
    with pytest.raises(UnknownEventTypeError):
        EventRegistry().deserialize(envelope)
