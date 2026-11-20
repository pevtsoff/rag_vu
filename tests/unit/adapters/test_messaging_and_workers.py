import asyncio
from uuid import uuid4

from app.adapters.inbound.celery_jobs import jobs
from app.adapters.inbound.celery_jobs.celery_app import celery_app
from app.adapters.inbound.event_processor.event_processor_loop import EventProcessorLoop
from app.adapters.outbound.messaging.celery_job_dispatcher import CeleryJobDispatcher
from app.application.dto.job_route import JobRoute

STAGES = ("upload", "parsing", "chunking", "embedding")


def test_each_stage_has_its_own_queue_and_task() -> None:
    assert {queue.name for queue in celery_app.conf.task_queues} == set(STAGES)
    for stage in STAGES:
        assert f"jobs.{stage}" in celery_app.tasks
        assert celery_app.conf.task_routes[f"jobs.{stage}"] == {"queue": stage}
    assert celery_app.conf.task_acks_late and celery_app.conf.worker_prefetch_multiplier == 1
    assert jobs.embedding_job.name == "jobs.embedding"


async def test_dispatcher_sends_only_the_inbox_id_to_the_stage_queue() -> None:
    sent: list[tuple] = []

    class Client:
        def send_task(self, name: str, args: list[str], queue: str) -> None:
            sent.append((name, args, queue))

    inbox_id = uuid4()
    await CeleryJobDispatcher(Client()).dispatch(JobRoute("chunking", "chunking"), inbox_id)
    assert sent == [("jobs.chunking", [str(inbox_id)], "chunking")]


class CountingStep:
    def __init__(self, results: list[int]) -> None:
        self.results = results
        self.calls = 0

    async def execute(self) -> int:
        self.calls += 1
        result = self.results.pop(0) if self.results else 0
        if isinstance(result, Exception):
            raise result
        return result


async def test_event_loop_keeps_relaying_while_there_is_work_and_survives_errors() -> None:
    relay = CountingStep([3, RuntimeError("database restarting"), 1])
    redelivery = CountingStep([])
    loop = EventProcessorLoop(relay, redelivery, poll_interval=0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(loop.run(stop))
    await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, 1)
    assert relay.calls >= 4
