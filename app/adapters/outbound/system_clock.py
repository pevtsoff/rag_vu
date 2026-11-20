from datetime import UTC, datetime

from app.application.ports.clock import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
