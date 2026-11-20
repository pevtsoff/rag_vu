"""Upload → parsing → chunking → embedding through PostgreSQL outbox and inbox tables."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.application.dto.job_outcome import JobOutcome
from app.application.errors import StageJobError
from app.application.use_cases.documents.rerun_pipeline import RerunPipeline
from app.bootstrap.infrastructure import Infrastructure
from app.domain.documents.pipeline_stage import PipelineStage
from tests.integration.pipeline_runner import PipelineRunner
from tests.unit.fakes.fake_ports import BytesStream, FakeParser


def _rows(engine: Engine, sql: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


async def test_an_upload_runs_all_four_stages(
    infrastructure: Infrastructure, sync_engine: Engine
) -> None:
    runner = PipelineRunner(infrastructure)
    result = await runner.upload.execute(BytesStream(b"pdf data"), "law.pdf", "application/pdf")

    assert await runner.drain() == ["upload", "parsing", "chunking", "embedding"]

    assert _rows(
        sync_engine, "SELECT event_type, producer, status FROM outbox_events ORDER BY occurred_at"
    ) == [
        ("FileReceivedEvent", "api", "PUBLISHED"),
        ("FileUploadedEvent", "upload", "PUBLISHED"),
        ("DocumentParsedEvent", "parsing", "PUBLISHED"),
        ("DocumentChunkedEvent", "chunking", "PUBLISHED"),
        ("DocumentEmbeddedEvent", "embedding", "PUBLISHED"),
    ]
    assert set(_rows(sync_engine, "SELECT consumer, status, attempts FROM inbox_events")) == {
        ("upload", "PROCESSED", 1),
        ("parsing", "PROCESSED", 1),
        ("chunking", "PROCESSED", 1),
        ("embedding", "PROCESSED", 1),
    }
    assert _rows(
        sync_engine, "SELECT stage, status, uploaded, parsed, chunked, embedded FROM pipelines"
    ) == [("embedding", "SUCCEEDED", True, True, True, True)]
    [(status, file_path)] = _rows(sync_engine, "SELECT status, file_path FROM documents")
    assert status == "SUCCEEDED" and file_path.endswith(f"{result.document.id}/law.pdf")
    assert _rows(sync_engine, "SELECT count(*), count(embedding_small) FROM chunks") == [(2, 2)]


async def test_uploaded_event_has_the_stored_file_details(
    infrastructure: Infrastructure, sync_engine: Engine
) -> None:
    runner = PipelineRunner(infrastructure)
    await runner.upload.execute(BytesStream(b"pdf data"), "law.pdf", "application/pdf")
    await runner.drain()
    [(payload,)] = _rows(
        sync_engine, "SELECT payload FROM outbox_events WHERE event_type = 'FileUploadedEvent'"
    )
    assert payload["size"] == 8 and len(payload["sha256"]) == 64
    assert payload["file_path"].endswith("/law.pdf") and payload["mime_type"] == "application/pdf"


async def test_concurrent_deliveries_of_one_message_process_it_once(
    infrastructure: Infrastructure,
) -> None:
    runner = PipelineRunner(infrastructure)
    await runner.upload.execute(BytesStream(b"pdf data"), "law.pdf", "application/pdf")
    await runner.relay.execute()
    [(route, inbox_id)] = runner.dispatcher.dispatched

    outcomes = await asyncio.gather(
        *(runner.runners[route.consumer].run(inbox_id) for _ in range(3))
    )

    assert sorted(outcomes) == sorted(
        [JobOutcome.PROCESSED, JobOutcome.ALREADY_HANDLED, JobOutcome.ALREADY_HANDLED]
    )
    assert await runner.runners[route.consumer].run(inbox_id) is JobOutcome.ALREADY_HANDLED


async def test_a_failed_stage_is_recorded_in_the_database(
    infrastructure: Infrastructure, sync_engine: Engine
) -> None:
    runner = PipelineRunner(infrastructure, parser=FakeParser(error=ValueError("unreadable file")))
    await runner.upload.execute(BytesStream(b"pdf data"), "law.pdf", "application/pdf")

    with pytest.raises(StageJobError):
        await runner.drain()

    [(status, stage, error)] = _rows(
        sync_engine, "SELECT status, error_stage, error_message FROM pipelines"
    )
    assert (status, stage) == ("FAILED", "parsing") and "unreadable file" in error
    assert _rows(sync_engine, "SELECT status FROM documents") == [("FAILED",)]
    assert ("parsing", "FAILED") in _rows(sync_engine, "SELECT consumer, status FROM inbox_events")
    assert ("PipelineFailedEvent",) in _rows(sync_engine, "SELECT event_type FROM outbox_events")


async def test_rerun_from_embedding_only_reembeds(
    infrastructure: Infrastructure, sync_engine: Engine
) -> None:
    runner = PipelineRunner(infrastructure)
    result = await runner.upload.execute(BytesStream(b"pdf data"), "law.pdf", "application/pdf")
    await runner.drain()
    chunk_ids = _rows(sync_engine, "SELECT id FROM chunks ORDER BY id")

    await RerunPipeline(infrastructure.unit_of_work).execute(
        result.document.id, PipelineStage.EMBEDDING, True
    )

    assert await runner.drain() == ["embedding"]
    assert _rows(sync_engine, "SELECT id FROM chunks ORDER BY id") == chunk_ids
    statuses = _rows(sync_engine, "SELECT status FROM pipelines ORDER BY created_at")
    assert statuses == [("SUCCEEDED",), ("SUCCEEDED",)]
