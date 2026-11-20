"""Dispatches inbox messages as Celery jobs; the message body is only the inbox id."""

import asyncio
from uuid import UUID

from celery import Celery

from app.adapters.outbound.messaging.celery_task_names import job_task_name
from app.application.dto.job_route import JobRoute
from app.application.ports.job_dispatcher import JobDispatcher


class CeleryJobDispatcher(JobDispatcher):
    def __init__(self, celery_app: Celery) -> None:
        self._celery_app = celery_app

    async def dispatch(self, route: JobRoute, inbox_id: UUID) -> None:
        await asyncio.to_thread(
            self._celery_app.send_task,
            job_task_name(route.consumer),
            args=[str(inbox_id)],
            queue=route.queue,
        )
