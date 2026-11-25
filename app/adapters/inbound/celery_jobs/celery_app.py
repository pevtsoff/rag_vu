"""Celery worker app: one queue per pipeline stage (``--queues=<stage>``)."""

from celery import Celery
from kombu import Queue

from app.adapters.outbound.messaging.celery_task_names import job_task_name
from app.application.use_cases.events.default_event_routes import default_event_routes
from app.config.app_settings import get_settings

ROUTES = default_event_routes()

celery_app = Celery(
    "rag_vu",
    broker=get_settings().celery_broker_url,
    include=["app.adapters.inbound.celery_jobs.jobs"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    # Inbox claims make redelivery safe, so acknowledge only after the job finished.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Task events feed Flower (task lists, timings, failures); they cost a few small messages.
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_queues=[
        Queue(ROUTES.route_for_consumer(name).queue) for name in sorted(ROUTES.consumers())
    ],
    task_routes={
        job_task_name(name): {"queue": ROUTES.route_for_consumer(name).queue}
        for name in ROUTES.consumers()
    },
)
