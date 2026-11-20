"""Hands an inbox message to the worker queue of its consumer."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.job_route import JobRoute


class JobDispatcher(ABC):
    @abstractmethod
    async def dispatch(self, route: JobRoute, inbox_id: UUID) -> None: ...
