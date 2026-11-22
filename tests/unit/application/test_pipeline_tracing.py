"""Every ingestion step leaves a span with the file details and what it produced."""

import json

import pytest

from app.application.errors import StageJobError
from app.application.tracing import trace_attributes as attr
from app.application.tracing.span_kind import SpanKind
from tests.unit.fakes.fake_ports import BytesStream, FakeParser
from tests.unit.fakes.pipeline_harness import PipelineHarness
from tests.unit.fakes.recording_span import RecordingSpan
from tests.unit.fakes.recording_tracer import RecordingTracer

STAGES = ["pipeline.upload", "pipeline.parsing", "pipeline.chunking", "pipeline.embedding"]


async def _ingest(tracer: RecordingTracer, parser: FakeParser | None = None) -> PipelineHarness:
    harness = PipelineHarness(parser=parser, tracer=tracer)
    await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")
    await harness.drain()
    return harness


def _assert_file_details(span: RecordingSpan, path: str) -> None:
    assert span.attributes[attr.FILE_NAME] == "law.pdf"
    assert span.attributes[attr.FILE_SIZE] == 4
    assert span.attributes[attr.FILE_PATH] == path


async def test_upload_request_records_file_and_starts_the_pipeline_session() -> None:
    tracer = RecordingTracer()
    harness = await _ingest(tracer)
    span = tracer.one("document.upload")
    [pipeline_id] = harness.store.pipelines

    assert span.parent is None and span.kind is SpanKind.CHAIN
    assert span.attributes[attr.FILE_NAME] == "law.pdf"
    assert span.attributes[attr.FILE_SIZE] == 4
    assert span.attributes[attr.STAGED_PATH] == "/incoming/law.pdf"
    assert span.attributes[attr.UPLOAD_DUPLICATE] is False
    assert span.session_id == str(pipeline_id)


async def test_each_stage_has_a_span_in_the_same_session() -> None:
    tracer = RecordingTracer()
    harness = await _ingest(tracer)
    [pipeline_id] = harness.store.pipelines

    stage_spans = [span for span in tracer.spans if span.name.startswith("pipeline.")]
    assert [span.name.split(" [")[0] for span in stage_spans] == STAGES
    assert {span.session_id for span in stage_spans} == {str(pipeline_id)}
    assert all(span.attributes[attr.JOB_OUTCOME] == "processed" for span in stage_spans)


async def test_stage_spans_record_file_details_and_counts() -> None:
    tracer = RecordingTracer()
    harness = await _ingest(tracer)
    [document] = harness.store.documents.values()
    stored = f"/documents/{document.id}/law.pdf"

    upload = tracer.one("pipeline.upload")
    _assert_file_details(upload, "/incoming/law.pdf")
    assert upload.attributes[attr.STORED_PATH] == stored
    parsing, chunking, embedding = (tracer.one(name) for name in STAGES[1:])
    for span in (parsing, chunking, embedding):
        _assert_file_details(span, stored)
    assert parsing.attributes[attr.PARSE_NODE_COUNT] == 2
    assert json.loads(parsing.attributes[attr.PARSE_NODE_TYPES]) == {"preamble": 1, "section": 1}
    assert chunking.attributes[attr.CHUNK_COUNT] == 2
    assert embedding.attributes[attr.EMBEDDING_COUNT] == 2
    assert embedding.attributes[attr.EMBEDDING_BATCH_COUNT] == 1


async def test_embedding_batches_are_child_spans_of_the_embedding_stage() -> None:
    tracer = RecordingTracer()
    await _ingest(tracer)
    [batch] = tracer.named("embedding.passage")

    assert batch.parent is tracer.one("pipeline.embedding")
    assert batch.kind is SpanKind.EMBEDDING and batch.model_name == "fake-embed"
    assert batch.attributes[attr.EMBEDDING_TEXT_COUNT] == 2


async def test_a_failing_stage_records_the_error_on_its_span() -> None:
    tracer = RecordingTracer()
    with pytest.raises(StageJobError):
        await _ingest(tracer, parser=FakeParser(error=ValueError("broken pdf")))

    parsing = tracer.one("pipeline.parsing")
    assert "broken pdf" in str(parsing.error)
    assert parsing.attributes[attr.FILE_NAME] == "law.pdf"
    assert not tracer.named("pipeline.chunking")


async def test_job_spans_carry_the_pipeline_id_in_name_and_attributes() -> None:
    tracer = RecordingTracer()
    harness = await _ingest(tracer)
    [pipeline_id] = harness.store.pipelines

    stage_spans = [tracer.one(name) for name in STAGES]
    assert [span.name for span in stage_spans] == [f"{name} [{pipeline_id}]" for name in STAGES]
    assert all(span.attributes[attr.PIPELINE_ID] == str(pipeline_id) for span in stage_spans)
    assert tracer.one("document.upload").name == f"document.upload [{pipeline_id}]"


async def test_each_job_is_still_a_trace_of_its_own() -> None:
    tracer = RecordingTracer()
    await _ingest(tracer)

    assert all(tracer.one(name).parent is None for name in STAGES)


async def test_a_finished_pipeline_sends_one_run_trace() -> None:
    tracer = RecordingTracer()
    harness = await _ingest(tracer)
    [pipeline_id] = harness.store.pipelines
    [document] = harness.store.documents.values()
    run = tracer.one_run(pipeline_id)

    assert run.status == "SUCCEEDED" and run.error is None
    assert run.ended_at == harness.clock.now()
    assert run.attributes[attr.PIPELINE_ID] == str(pipeline_id)
    assert run.attributes[attr.DOCUMENT_ID] == str(document.id)
    assert run.attributes[attr.FILE_NAME] == "law.pdf"
    assert run.attributes[attr.PIPELINE_STAGES_DONE] == [
        "uploading",
        "parsing",
        "chunking",
        "embedding",
    ]
    assert len(tracer.runs) == 1


async def test_a_failed_pipeline_sends_its_run_trace_with_the_error() -> None:
    tracer = RecordingTracer()
    with pytest.raises(StageJobError):
        await _ingest(tracer, parser=FakeParser(error=ValueError("broken pdf")))
    [run] = tracer.runs

    assert run.status == "FAILED"
    assert "broken pdf" in (run.error or "")
    assert run.attributes[attr.PIPELINE_ERROR_STAGE] == "parsing"
    assert run.attributes[attr.PIPELINE_STAGES_DONE] == ["uploading"]
