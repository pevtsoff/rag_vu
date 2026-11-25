"""Startup-only recovery: redeliver messages abandoned by a previous worker generation."""

from app.application.ports.clock import Clock
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher


class ReclaimOrphanedInboxMessages:
    """Immediately redeliver every still-``PROCESSING`` inbox message.

    Call this once, before a freshly started event processor begins its normal poll loop.
    If this process is starting, every worker that could hold one of these locks is gone
    (the whole docker compose stack restarted), so any message still marked ``PROCESSING``
    was abandoned mid-stage. The ordinary ``RedeliverInboxMessages`` sweep would eventually
    notice this too, but only after ``inbox_lock_timeout_seconds`` (the lock's own timeout),
    which can be long; redelivering right away gets the pipeline back onto its stage at once.

    This is safe even if a message is not actually orphaned (for instance, the event
    processor restarted alone while a worker elsewhere is still genuinely running the
    stage): InboxJobRunner's claim-then-acknowledge is a single optimistic-locking
    transaction, so whichever attempt finishes first wins the lock, and the other loses
    it and discards its result. The cost of a false positive is wasted duplicate work,
    never a correctness problem.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        dispatcher: DeliveryDispatcher,
        clock: Clock,
        batch_size: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._clock = clock
        self._batch_size = batch_size

    async def execute(self) -> int:
        """Return the number of messages reclaimed and handed to the dispatcher again."""
        total = 0
        while True:
            async with self._uow_factory() as uow:
                deliveries = await uow.inbox.release_orphaned_locks(
                    self._clock.now(), self._batch_size
                )
                await uow.commit()
            if not deliveries:
                return total
            await self._dispatcher.dispatch(deliveries)
            total += len(deliveries)
