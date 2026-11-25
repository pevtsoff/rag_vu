"""``python -m app.adapters.inbound.event_processor``"""

import asyncio
import logging
import signal

from app.adapters.inbound.event_processor.event_processor_loop import EventProcessorLoop
from app.bootstrap.event_processor_container import EventProcessorContainer
from app.bootstrap.infrastructure import Infrastructure
from app.config.app_settings import get_settings

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    infrastructure = Infrastructure(settings)
    container = EventProcessorContainer(infrastructure)
    loop = EventProcessorLoop(
        container.relay, container.redelivery, settings.event_poll_interval_seconds
    )
    stop = asyncio.Event()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(signal_number, stop.set)
    try:
        # One-off recovery: anything still PROCESSING predates this process, so it was
        # abandoned by a worker that can no longer exist (see ReclaimOrphanedInboxMessages).
        reclaimed = await container.startup_reclaim.execute()
        if reclaimed:
            logger.info("Reclaimed %s inbox message(s) left mid-stage by the previous run", reclaimed)
        await loop.run(stop)
    finally:
        await infrastructure.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
