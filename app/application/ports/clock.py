"""Source of the current time."""

from abc import ABC, abstractmethod
from datetime import datetime


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
