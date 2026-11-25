"""All four stages, event by event, with in-memory adapters."""

from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.documents.pipeline_status import PipelineStatus
from tests.unit.fakes.fake_ports import BytesStream
from tests.unit.fakes.pipeline_harness import PipelineHarness

EXPECTED_EVENTS = [
    "FileReceivedEvent",
    "FileUploadedEvent",
    "DocumentParsedEvent",
    "DocumentChunkedEvent",
    "DocumentEmbeddedEvent",
    "DocumentVersionedEvent",
]


async def test_upload_flows_through_every_stage_and_succeeds() -> None:
    harness = PipelineHarness()
    result = await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")

    order = await harness.drain()

    assert order == ["upload", "parsing", "chunking", "embedding", "versioning"]
    assert harness.store.outbox_types() == EXPECTED_EVENTS
    assert set(harness.store.outbox) == harness.store.published
    assert all(record.status == "PROCESSED" for record in harness.store.inbox.values())
    pipeline = harness.store.pipelines[result.pipeline.id]
    assert pipeline.status is PipelineStatus.SUCCEEDED
    assert (pipeline.uploaded, pipeline.parsed, pipeline.chunked, pipeline.embedded) == (True,) * 4
    assert pipeline.versioned
    document = harness.store.documents[result.document.id]
    assert document.status is PipelineStatus.SUCCEEDED
    assert document.file_path == f"/documents/{document.id}/law.pdf"
    assert document.structure_path == f"{document.file_path}.docling.json"


async def test_events_carry_file_details_and_counts() -> None:
    harness = PipelineHarness()
    await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")
    await harness.drain()
    payloads = {e.event_type: (e.producer, e.payload) for e in harness.store.outbox.values()}

    producer, uploaded = payloads["FileUploadedEvent"]
    assert producer == "upload"
    assert (uploaded["size"], uploaded["sha256"], uploaded["mime_type"]) == (
        4,
        "sha",
        "application/pdf",
    )
    assert payloads["DocumentParsedEvent"][1]["node_count"] == 2
    assert payloads["DocumentChunkedEvent"][1]["chunk_count"] == 2
    assert payloads["DocumentEmbeddedEvent"][1]["dimensions"] == 768


async def test_chunking_receives_the_structure_path_and_embedding_runs_in_batches() -> None:
    harness = PipelineHarness()
    await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")
    await harness.drain()
    assert harness.chunker.structure_paths[0].endswith("law.pdf.docling.json")
    assert [len(texts) for texts, _ in harness.embedder.calls] == [2]
    assert {task for _, task in harness.embedder.calls} == {EmbeddingTask.PASSAGE}
    assert len(harness.store.vectors) == 2


async def test_a_replaced_run_does_not_advance_after_a_newer_run_starts() -> None:
    harness = PipelineHarness()
    first = await harness.upload.execute(BytesStream(b"data"), "law.pdf", "application/pdf")
    second = await harness.upload.execute(
        BytesStream(b"data"), "copy.pdf", "application/pdf", force_run=True
    )

    await harness.drain()

    assert harness.store.pipelines[first.pipeline.id].status is PipelineStatus.CANCELLED
    assert harness.store.pipelines[second.pipeline.id].status is PipelineStatus.SUCCEEDED
    assert harness.store.outbox_types().count("DocumentEmbeddedEvent") == 1
