"""Sends inbox deliveries to their worker queues."""

import logging
from uuid import UUID

from app.application.dto.inbox_delivery import InboxDelivery
from app.application.ports.job_dispatcher import JobDispatcher
from app.application.use_cases.events.event_routes import EventRoutes

logger = logging.getLogger(__name__)


class DeliveryDispatcher:
    def __init__(self, dispatcher: JobDispatcher, routes: EventRoutes) -> None:
        self._dispatcher = dispatcher
        self._routes = routes

    async def dispatch(self, deliveries: list[InboxDelivery]) -> list[UUID]:
        """Dispatch each delivery; return the ids that reached the broker.

        A failed dispatch is logged and left for redelivery: the message is safe in the
        inbox table, so a broker outage only delays processing.
        """
        sent: list[UUID] = []
        for delivery in deliveries:
            route = self._routes.route_for_consumer(delivery.consumer)
            try:
                await self._dispatcher.dispatch(route, delivery.inbox_id)
            except Exception:
                logger.exception("Dispatch of inbox message %s failed", delivery.inbox_id)
                continue
            sent.append(delivery.inbox_id)
        return sent
