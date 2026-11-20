"""Runs an inbox job inside a synchronous Celery task."""

import asyncio
from functools import lru_cache
from uuid import UUID

from app.bootstrap.infrastructure import Infrastructure
from app.bootstrap.worker_container import WorkerContainer
from app.config.app_settings import get_settings


@lru_cache
def worker_container() -> WorkerContainer:
    # Each task gets a fresh event loop, so connections must not be pooled across tasks.
    return WorkerContainer(Infrastructure(get_settings(), null_pool=True))


def run_inbox_job(consumer: str, inbox_id: str) -> str:
    runner = worker_container().inbox_job_runner(consumer)
    return str(asyncio.run(runner.run(UUID(inbox_id))))
