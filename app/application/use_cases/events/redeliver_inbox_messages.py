"""Re-dispatch inbox messages whose job never ran or whose worker died."""

from datetime import timedelta

from app.application.ports.clock import Clock
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher


class RedeliverInboxMessages:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        dispatcher: DeliveryDispatcher,
        clock: Clock,
        redeliver_after: timedelta,
        batch_size: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._clock = clock
        self._redeliver_after = redeliver_after
        self._batch_size = batch_size

    async def execute(self) -> int:
        """Return the number of messages handed to the dispatcher again."""
        now = self._clock.now()
        async with self._uow_factory() as uow:
            deliveries = await uow.inbox.lock_redeliverable(
                now, now - self._redeliver_after, self._batch_size
            )
            await uow.commit()
        if deliveries:
            await self._dispatcher.dispatch(deliveries)
        return len(deliveries)
