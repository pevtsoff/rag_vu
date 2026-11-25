"""Transactional outbox and idempotent inbox semantics on real PostgreSQL."""

from datetime import timedelta
from uuid import uuid4

from app.bootstrap.infrastructure import Infrastructure
from app.domain.events.document_chunked_event import DocumentChunkedEvent
from app.domain.events.event_envelope import EventEnvelope


def _envelope() -> EventEnvelope:
    return EventEnvelope.from_event(
        DocumentChunkedEvent(
            producer="chunking", document_id=uuid4(), pipeline_id=uuid4(), chunk_count=1
        )
    )


async def _add(infrastructure: Infrastructure, count: int) -> list[EventEnvelope]:
    envelopes = [_envelope() for _ in range(count)]
    async with infrastructure.unit_of_work() as uow:
        await uow.outbox.add(envelopes)
        await uow.commit()
    return envelopes


async def test_events_are_not_stored_when_the_transaction_rolls_back(
    infrastructure: Infrastructure,
) -> None:
    async with infrastructure.unit_of_work() as uow:
        await uow.outbox.add([_envelope()])
    async with infrastructure.unit_of_work() as uow:
        assert await uow.outbox.lock_pending(10) == []


async def test_concurrent_relays_skip_rows_locked_by_each_other(
    infrastructure: Infrastructure,
) -> None:
    envelopes = await _add(infrastructure, 3)
    async with infrastructure.unit_of_work() as first, infrastructure.unit_of_work() as second:
        locked_by_first = await first.outbox.lock_pending(2)
        locked_by_second = await second.outbox.lock_pending(10)
    first_ids = {e.event_id for e in locked_by_first}
    second_ids = {e.event_id for e in locked_by_second}
    assert len(first_ids) == 2 and len(second_ids) == 1
    assert first_ids | second_ids == {e.event_id for e in envelopes}


async def test_published_events_are_not_relayed_again(infrastructure: Infrastructure) -> None:
    envelopes = await _add(infrastructure, 2)
    async with infrastructure.unit_of_work() as uow:
        await uow.outbox.mark_published([envelopes[0].event_id], infrastructure.clock.now())
        await uow.commit()
    async with infrastructure.unit_of_work() as uow:
        [pending] = await uow.outbox.lock_pending(10)
    assert pending == envelopes[1]


async def test_inbox_receives_each_event_once_per_consumer(infrastructure: Infrastructure) -> None:
    envelope = _envelope()
    now = infrastructure.clock.now()
    async with infrastructure.unit_of_work() as uow:
        first = await uow.inbox.receive(envelope, "embedding", now)
        again = await uow.inbox.receive(envelope, "embedding", now)
        other_consumer = await uow.inbox.receive(envelope, "audit", now)
        await uow.commit()
    assert first is not None and again is None and other_consumer not in (None, first)


async def test_claim_complete_and_lock_tokens(infrastructure: Infrastructure) -> None:
    now = infrastructure.clock.now()
    async with infrastructure.unit_of_work() as uow:
        inbox_id = await uow.inbox.receive(_envelope(), "embedding", now)
        await uow.commit()
    token, intruder = uuid4(), uuid4()
    async with infrastructure.unit_of_work() as uow:
        message = await uow.inbox.claim(inbox_id, token, now, now + timedelta(minutes=5))
        assert await uow.inbox.claim(inbox_id, intruder, now, now + timedelta(minutes=5)) is None
        assert not await uow.inbox.complete(inbox_id, intruder, now)
        assert await uow.inbox.complete(inbox_id, token, now)
        await uow.commit()
    assert (message.attempts, message.envelope.event_type) == (1, "DocumentChunkedEvent")
    async with infrastructure.unit_of_work() as uow:
        assert await uow.inbox.claim(inbox_id, uuid4(), now, now + timedelta(minutes=5)) is None


async def test_expired_locks_and_lost_dispatches_are_redelivered(
    infrastructure: Infrastructure,
) -> None:
    now = infrastructure.clock.now()
    later = now + timedelta(hours=1)
    async with infrastructure.unit_of_work() as uow:
        lost = await uow.inbox.receive(_envelope(), "embedding", now)
        abandoned = await uow.inbox.receive(_envelope(), "chunking", now)
        fresh = await uow.inbox.receive(_envelope(), "parsing", later)
        await uow.inbox.claim(abandoned, uuid4(), now, now + timedelta(minutes=1))
        await uow.commit()
    async with infrastructure.unit_of_work() as uow:
        deliveries = await uow.inbox.lock_redeliverable(later, later - timedelta(minutes=5), 10)
        await uow.commit()
    assert {d.inbox_id for d in deliveries} == {lost, abandoned}
    assert fresh not in {d.inbox_id for d in deliveries}
    async with infrastructure.unit_of_work() as uow:
        assert await uow.inbox.lock_redeliverable(later, later - timedelta(minutes=5), 10) == []


async def test_release_orphaned_locks_redelivers_processing_messages_right_away(
    infrastructure: Infrastructure,
) -> None:
    now = infrastructure.clock.now()
    async with infrastructure.unit_of_work() as uow:
        stuck = await uow.inbox.receive(_envelope(), "embedding", now)
        waiting = await uow.inbox.receive(_envelope(), "parsing", now)
        # Locked for the next hour: a short time later is not enough for lock_redeliverable.
        await uow.inbox.claim(stuck, uuid4(), now, now + timedelta(hours=1))
        await uow.commit()
    soon = now + timedelta(seconds=1)
    async with infrastructure.unit_of_work() as uow:
        assert await uow.inbox.lock_redeliverable(soon, soon - timedelta(minutes=5), 10) == []
        deliveries = await uow.inbox.release_orphaned_locks(soon, 10)
        await uow.commit()
    assert {d.inbox_id for d in deliveries} == {stuck}
    assert waiting not in {d.inbox_id for d in deliveries}
    async with infrastructure.unit_of_work() as uow:
        # Now claimable again, as a freshly received message would be.
        assert await uow.inbox.claim(stuck, uuid4(), soon, soon + timedelta(hours=1)) is not None
