"""Outbox relay and inbox redelivery for the event processor."""

from datetime import timedelta
from functools import cached_property

from app.adapters.outbound.messaging.celery_client import create_celery_client
from app.adapters.outbound.messaging.celery_job_dispatcher import CeleryJobDispatcher
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher
from app.application.use_cases.events.redeliver_inbox_messages import RedeliverInboxMessages
from app.application.use_cases.events.relay_outbox_batch import RelayOutboxBatch
from app.bootstrap.infrastructure import Infrastructure


class EventProcessorContainer:
    def __init__(self, infrastructure: Infrastructure) -> None:
        self.infrastructure = infrastructure
        self._settings = infrastructure.settings

    @cached_property
    def delivery_dispatcher(self) -> DeliveryDispatcher:
        celery_client = create_celery_client(self._settings.celery_broker_url)
        return DeliveryDispatcher(
            CeleryJobDispatcher(celery_client), self.infrastructure.event_routes
        )

    @cached_property
    def relay(self) -> RelayOutboxBatch:
        return RelayOutboxBatch(
            self.infrastructure.unit_of_work,
            self.infrastructure.event_routes,
            self.delivery_dispatcher,
            self.infrastructure.clock,
            self._settings.event_batch_size,
        )

    @cached_property
    def redelivery(self) -> RedeliverInboxMessages:
        return RedeliverInboxMessages(
            self.infrastructure.unit_of_work,
            self.delivery_dispatcher,
            self.infrastructure.clock,
            timedelta(seconds=self._settings.inbox_redelivery_after_seconds),
            self._settings.event_batch_size,
        )
