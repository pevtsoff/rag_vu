from celery import Celery


def create_celery_client(broker_url: str) -> Celery:
    """A producer-only Celery app; it sends jobs by name and needs no task code."""
    client = Celery("rag_vu-producer", broker=broker_url)
    client.conf.update(task_serializer="json", accept_content=["json"], task_ignore_result=True)
    return client
