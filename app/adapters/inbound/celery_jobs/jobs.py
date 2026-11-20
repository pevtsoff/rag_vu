"""One Celery task per pipeline stage. Each receives only an inbox message id."""

from app.adapters.inbound.celery_jobs.celery_app import celery_app
from app.adapters.inbound.celery_jobs.job_runtime import run_inbox_job
from app.adapters.outbound.messaging.celery_task_names import job_task_name
from app.application.use_cases.events.default_event_routes import (
    CHUNKING_ROUTE,
    EMBEDDING_ROUTE,
    PARSING_ROUTE,
    UPLOAD_ROUTE,
)


@celery_app.task(name=job_task_name(UPLOAD_ROUTE.consumer))
def upload_job(inbox_id: str) -> str:
    return run_inbox_job(UPLOAD_ROUTE.consumer, inbox_id)


@celery_app.task(name=job_task_name(PARSING_ROUTE.consumer))
def parsing_job(inbox_id: str) -> str:
    return run_inbox_job(PARSING_ROUTE.consumer, inbox_id)


@celery_app.task(name=job_task_name(CHUNKING_ROUTE.consumer))
def chunking_job(inbox_id: str) -> str:
    return run_inbox_job(CHUNKING_ROUTE.consumer, inbox_id)


@celery_app.task(name=job_task_name(EMBEDDING_ROUTE.consumer))
def embedding_job(inbox_id: str) -> str:
    return run_inbox_job(EMBEDDING_ROUTE.consumer, inbox_id)
