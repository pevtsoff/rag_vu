from uuid import uuid4

from app.application.use_cases.events.default_event_routes import default_event_routes
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher
from app.application.use_cases.events.relay_outbox_batch import RelayOutboxBatch
from app.domain.events.document_embedded_event import DocumentEmbeddedEvent
from app.domain.events.event_envelope import EventEnvelope
from app.domain.events.file_uploaded_event import FileUploadedEvent
from tests.unit.fakes.fake_clock import FakeClock
from tests.unit.fakes.fake_ports import RecordingDispatcher
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory


def _uploaded() -> EventEnvelope:
    return EventEnvelope.from_event(
        FileUploadedEvent(
            producer="upload",
            document_id=uuid4(),
            pipeline_id=uuid4(),
            file_path="/f",
            file_name="f",
            size=1,
            sha256="s",
            mime_type="text/plain",
        )
    )


def _relay(
    store: InMemoryStore, dispatcher: RecordingDispatcher, batch: int = 10
) -> RelayOutboxBatch:
    routes = default_event_routes()
    return RelayOutboxBatch(
        uow_factory(store), routes, DeliveryDispatcher(dispatcher, routes), FakeClock(), batch
    )


async def test_relay_copies_events_to_inbox_and_dispatches_to_the_stage_queue() -> None:
    store, dispatcher = InMemoryStore(), RecordingDispatcher()
    envelope = _uploaded()
    store.outbox[envelope.event_id] = envelope

    assert await _relay(store, dispatcher).execute() == 1

    [record] = store.inbox.values()
    assert (record.consumer, record.envelope.event_id) == ("parsing", envelope.event_id)
    assert record.dispatched_at is not None
    [(route, inbox_id)] = dispatcher.dispatched
    assert (route.queue, inbox_id) == ("parsing", record.id)
    assert store.published == {envelope.event_id}


async def test_relaying_the_same_event_again_creates_no_second_delivery() -> None:
    store, dispatcher = InMemoryStore(), RecordingDispatcher()
    envelope = _uploaded()
    store.outbox[envelope.event_id] = envelope
    await _relay(store, dispatcher).execute()
    store.published.clear()  # e.g. the PUBLISHED mark was lost and the event is relayed again

    await _relay(store, dispatcher).execute()

    assert len(store.inbox) == 1
    assert len(dispatcher.dispatched) == 1


async def test_events_without_consumers_are_only_marked_published() -> None:
    store, dispatcher = InMemoryStore(), RecordingDispatcher()
    envelope = EventEnvelope.from_event(
        DocumentEmbeddedEvent(
            producer="embedding",
            document_id=uuid4(),
            pipeline_id=uuid4(),
            chunk_count=1,
            dimensions=768,
        )
    )
    store.outbox[envelope.event_id] = envelope
    assert await _relay(store, dispatcher).execute() == 1
    assert store.inbox == {} and dispatcher.dispatched == []
    assert envelope.event_id in store.published


async def test_relay_respects_the_batch_size() -> None:
    store, dispatcher = InMemoryStore(), RecordingDispatcher()
    for _ in range(3):
        envelope = _uploaded()
        store.outbox[envelope.event_id] = envelope
    relay = _relay(store, dispatcher, batch=2)
    assert [await relay.execute() for _ in range(3)] == [2, 1, 0]


async def test_broker_failure_keeps_the_inbox_row_undispatched_for_redelivery() -> None:
    store = InMemoryStore()
    envelope = _uploaded()
    store.outbox[envelope.event_id] = envelope
    await _relay(store, RecordingDispatcher(failing=True)).execute()
    [record] = store.inbox.values()
    assert record.status == "RECEIVED" and record.dispatched_at is None
    assert envelope.event_id in store.published
