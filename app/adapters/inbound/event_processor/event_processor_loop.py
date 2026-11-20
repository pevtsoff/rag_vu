import asyncio
import logging

from app.application.use_cases.events.redeliver_inbox_messages import RedeliverInboxMessages
from app.application.use_cases.events.relay_outbox_batch import RelayOutboxBatch

logger = logging.getLogger(__name__)


class EventProcessorLoop:
    """Relays batches back to back while there is work, then polls at ``poll_interval``."""

    def __init__(
        self, relay: RelayOutboxBatch, redelivery: RedeliverInboxMessages, poll_interval: float
    ) -> None:
        self._relay = relay
        self._redelivery = redelivery
        self._poll_interval = poll_interval

    async def run_once(self) -> int:
        relayed = await self._relay.execute()
        redelivered = await self._redelivery.execute()
        if relayed or redelivered:
            logger.info("Relayed %s events, redelivered %s messages", relayed, redelivered)
        return relayed + redelivered

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                handled = await self.run_once()
            except Exception:
                # The database may be restarting; events are durable, so retry later.
                logger.exception("Event processing iteration failed")
                handled = 0
            if not handled:
                await _wait(stop, self._poll_interval)


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass
