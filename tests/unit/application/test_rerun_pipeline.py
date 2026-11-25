from uuid import uuid4

import pytest

from app.application.errors import DocumentNotFoundError, NoActivePipelineError
from app.application.use_cases.documents.rerun_pipeline import RerunPipeline
from app.domain.documents.chunk import Chunk
from app.domain.documents.document import Document
from app.domain.documents.node import Node
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory
from tests.unit.fakes.recording_tracer import RecordingTracer

TRIGGERS = {
    PipelineStage.UPLOADING: "FileReceivedEvent",
    PipelineStage.PARSING: "FileUploadedEvent",
    PipelineStage.CHUNKING: "DocumentParsedEvent",
    PipelineStage.EMBEDDING: "DocumentChunkedEvent",
    PipelineStage.VERSIONING: "DocumentEmbeddedEvent",
}


def _store(active: bool = False) -> tuple[InMemoryStore, Document, Pipeline]:
    store = InMemoryStore()
    document = Document(
        file_name="law.pdf",
        file_path="/d/law.pdf",
        size=1,
        sha256="s",
        mime_type="application/pdf",
        structure_path="/d/law.pdf.docling.json",
        status=PipelineStatus.SUCCEEDED,
    )
    pipeline = Pipeline.start(document.id, PipelineStage.PARSING)
    if not active:
        pipeline.status = PipelineStatus.SUCCEEDED
    node = Node(document_id=document.id, node_type="section", text="Text", path="p1")
    store.documents[document.id] = document
    store.pipelines[pipeline.id] = pipeline
    store.nodes[node.id] = node
    store.chunks[uuid4()] = Chunk(uuid4(), node.id, 0, "Text")
    return store, document, pipeline


@pytest.mark.parametrize("stage", list(PipelineStage))
async def test_forced_rerun_emits_the_event_that_starts_the_stage(stage: PipelineStage) -> None:
    store, document, _ = _store()

    pipeline = await RerunPipeline(uow_factory(store)).execute(document.id, stage, force_run=True)

    assert pipeline.stage is stage and pipeline.is_active
    assert store.documents[document.id].status is PipelineStatus.IN_PROGRESS
    [envelope] = store.outbox.values()
    assert envelope.event_type == TRIGGERS[stage]
    assert envelope.payload["pipeline_id"] == str(pipeline.id)


async def test_chunking_trigger_carries_the_structure_path() -> None:
    store, document, _ = _store()
    await RerunPipeline(uow_factory(store)).execute(document.id, PipelineStage.CHUNKING, True)
    [envelope] = store.outbox.values()
    assert envelope.payload["structure_path"] == "/d/law.pdf.docling.json"


async def test_embedding_trigger_counts_existing_chunks() -> None:
    store, document, _ = _store()
    await RerunPipeline(uow_factory(store)).execute(document.id, PipelineStage.EMBEDDING, True)
    [envelope] = store.outbox.values()
    assert envelope.payload["chunk_count"] == 1


async def test_without_force_the_active_pipeline_is_returned() -> None:
    store, document, active = _store(active=True)
    pipeline = await RerunPipeline(uow_factory(store)).execute(document.id, PipelineStage.PARSING)
    assert pipeline.id == active.id
    assert store.outbox == {}


async def test_without_force_and_without_active_pipeline_is_a_conflict() -> None:
    store, document, _ = _store()
    with pytest.raises(NoActivePipelineError):
        await RerunPipeline(uow_factory(store)).execute(document.id, PipelineStage.PARSING)


async def test_forced_rerun_cancels_the_active_pipeline() -> None:
    store, document, active = _store(active=True)
    pipeline = await RerunPipeline(uow_factory(store)).execute(
        document.id, PipelineStage.PARSING, force_run=True
    )
    assert store.pipelines[active.id].status is PipelineStatus.CANCELLED
    assert pipeline.id != active.id


async def test_missing_document_is_not_found() -> None:
    with pytest.raises(DocumentNotFoundError):
        await RerunPipeline(uow_factory(InMemoryStore())).execute(uuid4(), PipelineStage.PARSING)


async def test_forced_rerun_sends_the_run_trace_of_the_cancelled_run() -> None:
    store, document, active = _store(active=True)
    tracer = RecordingTracer()

    await RerunPipeline(uow_factory(store), tracer=tracer).execute(
        document.id, PipelineStage.PARSING, force_run=True
    )

    run = tracer.one_run(active.id)
    assert run.status == "CANCELLED"
    assert run.attributes["rag.document.id"] == str(document.id)


async def test_a_rerun_without_an_active_run_sends_no_run_trace() -> None:
    store, document, _ = _store()
    tracer = RecordingTracer()

    await RerunPipeline(uow_factory(store), tracer=tracer).execute(
        document.id, PipelineStage.PARSING, force_run=True
    )

    assert tracer.runs == []
