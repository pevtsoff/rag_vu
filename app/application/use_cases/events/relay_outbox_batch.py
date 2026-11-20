"""Move one batch of outbox events into consumer inboxes and dispatch their jobs."""

from datetime import datetime

from app.application.dto.inbox_delivery import InboxDelivery
from app.application.ports.clock import Clock
from app.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher
from app.application.use_cases.events.event_routes import EventRoutes
from app.domain.events.event_envelope import EventEnvelope


class RelayOutboxBatch:
    """The event processor's main step.

    Inbox rows are inserted with ON CONFLICT DO NOTHING on (event_id, consumer), so relaying
    the same event twice never creates a second delivery. Jobs are dispatched only after the
    transaction commits, so a worker can always find its inbox row.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        routes: EventRoutes,
        dispatcher: DeliveryDispatcher,
        clock: Clock,
        batch_size: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._routes = routes
        self._dispatcher = dispatcher
        self._clock = clock
        self._batch_size = batch_size

    async def execute(self) -> int:
        """Relay up to one batch; return the number of outbox events relayed."""
        async with self._uow_factory() as uow:
            envelopes = await uow.outbox.lock_pending(self._batch_size)
            deliveries = await self._receive_all(uow, envelopes)
            await uow.outbox.mark_published([item.event_id for item in envelopes], self._now())
            await uow.commit()
        await self._dispatch(deliveries)
        return len(envelopes)

    async def _receive_all(
        self, uow: UnitOfWork, envelopes: list[EventEnvelope]
    ) -> list[InboxDelivery]:
        deliveries: list[InboxDelivery] = []
        for envelope in envelopes:
            for route in self._routes.routes_for(envelope.event_type):
                inbox_id = await uow.inbox.receive(envelope, route.consumer, self._now())
                if inbox_id is not None:
                    deliveries.append(InboxDelivery(inbox_id, route.consumer))
        return deliveries

    async def _dispatch(self, deliveries: list[InboxDelivery]) -> None:
        if not deliveries:
            return
        sent = await self._dispatcher.dispatch(deliveries)
        if sent:
            async with self._uow_factory() as uow:
                await uow.inbox.mark_dispatched(sent, self._now())
                await uow.commit()

    def _now(self) -> datetime:
        return self._clock.now()
