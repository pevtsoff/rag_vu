"""Naming convention shared by the job dispatcher and the Celery workers."""

JOB_TASK_PREFIX = "jobs."


def job_task_name(consumer: str) -> str:
    return f"{JOB_TASK_PREFIX}{consumer}"
