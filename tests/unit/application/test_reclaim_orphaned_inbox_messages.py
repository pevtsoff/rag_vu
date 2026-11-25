from datetime import timedelta
from uuid import uuid4

from app.application.use_cases.events.default_event_routes import default_event_routes
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher
from app.application.use_cases.events.reclaim_orphaned_inbox_messages import (
    ReclaimOrphanedInboxMessages,
)
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


def _reclaim(
    store: InMemoryStore, dispatcher: RecordingDispatcher, batch: int = 10
) -> ReclaimOrphanedInboxMessages:
    routes = default_event_routes()
    return ReclaimOrphanedInboxMessages(
        uow_factory(store), DeliveryDispatcher(dispatcher, routes), FakeClock(), batch
    )


async def test_a_still_processing_message_is_redelivered_right_away() -> None:
    store, dispatcher = InMemoryStore(), RecordingDispatcher()
    clock = FakeClock()
    now = clock.now()
    async with uow_factory(store)() as uow:
        inbox_id = await uow.inbox.receive(_uploaded(), "parsing", now)
        await uow.inbox.claim(inbox_id, uuid4(), now, now + timedelta(hours=1))
        await uow.commit()

    reclaimed = await _reclaim(store, dispatcher).execute()

    assert reclaimed == 1
    [(route, dispatched_id)] = dispatcher.dispatched
    assert (route.queue, dispatched_id) == ("parsing", inbox_id)
    record = store.inbox[inbox_id]
    assert record.status == "RECEIVED" and record.locked_until is None


async def test_received_and_processed_messages_are_left_alone() -> None:
    store, dispatcher = InMemoryStore(), RecordingDispatcher()
    now = FakeClock().now()
    async with uow_factory(store)() as uow:
        waiting = await uow.inbox.receive(_uploaded(), "parsing", now)
        done_id = await uow.inbox.receive(_uploaded(), "parsing", now)
        token = uuid4()
        await uow.inbox.claim(done_id, token, now, now + timedelta(hours=1))
        await uow.inbox.complete(done_id, token, now)
        await uow.commit()

    assert await _reclaim(store, dispatcher).execute() == 0
    assert dispatcher.dispatched == []
    assert store.inbox[waiting].status == "RECEIVED"
    assert store.inbox[done_id].status == "PROCESSED"


async def test_reclaim_loops_over_batches_until_nothing_is_left() -> None:
    store, dispatcher = InMemoryStore(), RecordingDispatcher()
    now = FakeClock().now()
    async with uow_factory(store)() as uow:
        for _ in range(3):
            inbox_id = await uow.inbox.receive(_uploaded(), "parsing", now)
            await uow.inbox.claim(inbox_id, uuid4(), now, now + timedelta(hours=1))
        await uow.commit()

    assert await _reclaim(store, dispatcher, batch=1).execute() == 3
    assert len(dispatcher.dispatched) == 3
