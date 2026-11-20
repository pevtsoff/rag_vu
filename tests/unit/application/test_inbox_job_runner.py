from datetime import timedelta
from uuid import UUID

import pytest

from app.application.dto.job_outcome import JobOutcome
from app.application.dto.job_route import JobRoute
from app.application.dto.upload_result import UploadResult
from app.application.errors import StageJobError
from app.application.use_cases.events.default_event_routes import default_event_routes
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher
from app.application.use_cases.events.redeliver_inbox_messages import RedeliverInboxMessages
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus
from tests.unit.fakes.fake_ports import BytesStream, FakeParser
from tests.unit.fakes.pipeline_harness import PipelineHarness


async def _uploaded_and_relayed(harness: PipelineHarness) -> tuple[UploadResult, JobRoute, UUID]:
    result = await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")
    await harness.relay.execute()
    [(route, inbox_id)] = harness.dispatcher.dispatched
    harness.dispatcher.dispatched.clear()
    return result, route, inbox_id


async def test_a_job_runs_once_even_when_delivered_twice() -> None:
    harness = PipelineHarness()
    result, route, inbox_id = await _uploaded_and_relayed(harness)
    runner = harness.runners[route.consumer]

    assert await runner.run(inbox_id) is JobOutcome.PROCESSED
    assert await runner.run(inbox_id) is JobOutcome.ALREADY_HANDLED

    assert len(harness.storage.promoted) == 1
    assert harness.store.outbox_types().count("FileUploadedEvent") == 1
    assert harness.store.inbox[inbox_id].status == "PROCESSED"
    assert harness.store.pipelines[result.pipeline.id].stage is PipelineStage.PARSING


async def test_a_message_locked_by_another_worker_is_not_processed() -> None:
    harness = PipelineHarness()
    _, route, inbox_id = await _uploaded_and_relayed(harness)
    record = harness.store.inbox[inbox_id]
    record.status, record.locked_until = "PROCESSING", harness.clock.now() + timedelta(minutes=1)

    assert await harness.runners[route.consumer].run(inbox_id) is JobOutcome.ALREADY_HANDLED
    assert harness.storage.promoted == []


async def test_an_abandoned_message_can_be_reclaimed_after_its_lock_expires() -> None:
    harness = PipelineHarness()
    _, route, inbox_id = await _uploaded_and_relayed(harness)
    record = harness.store.inbox[inbox_id]
    record.status, record.locked_until = "PROCESSING", harness.clock.now() - timedelta(seconds=1)

    assert await harness.runners[route.consumer].run(inbox_id) is JobOutcome.PROCESSED


async def test_event_of_a_cancelled_pipeline_is_acknowledged_without_effect() -> None:
    harness = PipelineHarness()
    result, route, inbox_id = await _uploaded_and_relayed(harness)
    harness.store.pipelines[result.pipeline.id].cancel()

    assert await harness.runners[route.consumer].run(inbox_id) is JobOutcome.SKIPPED
    assert harness.storage.promoted == []
    assert harness.store.inbox[inbox_id].status == "PROCESSED"
    assert "FileUploadedEvent" not in harness.store.outbox_types()


async def test_a_failing_stage_fails_the_message_pipeline_and_document() -> None:
    harness = PipelineHarness(parser=FakeParser(error=RuntimeError("docling crashed")))
    result = await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")

    with pytest.raises(StageJobError, match="docling crashed"):
        await harness.drain()

    pipeline = harness.store.pipelines[result.pipeline.id]
    assert pipeline.status is PipelineStatus.FAILED and pipeline.error_stage == "parsing"
    assert "docling crashed" in pipeline.error_message
    assert harness.store.documents[result.document.id].status is PipelineStatus.FAILED
    failed = [r for r in harness.store.inbox.values() if r.consumer == "parsing"]
    assert failed[0].status == "FAILED"
    assert harness.store.outbox_types()[-1] == "PipelineFailedEvent"


async def test_redelivery_resends_lost_jobs_after_the_threshold_only() -> None:
    harness = PipelineHarness()
    await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")
    harness.dispatcher.failing = True
    await harness.relay.execute()
    harness.dispatcher.failing = False
    routes = default_event_routes()
    redelivery = RedeliverInboxMessages(
        harness.uow,
        DeliveryDispatcher(harness.dispatcher, routes),
        harness.clock,
        timedelta(seconds=60),
        10,
    )

    assert await redelivery.execute() == 0
    harness.clock.advance(61)
    assert await redelivery.execute() == 1
    assert await redelivery.execute() == 0  # stamped as dispatched again
    [(route, _)] = harness.dispatcher.dispatched
    assert route.consumer == "upload"
