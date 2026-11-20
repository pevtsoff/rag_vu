from app.application.use_cases.documents.upload_document import UploadDocument
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus
from app.domain.events.file_received_event import FileReceivedEvent
from tests.unit.fakes.fake_ports import BytesStream, FakeStorage
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory
from tests.unit.fakes.recording_tracer import RecordingTracer


def _use_case(store: InMemoryStore, storage: FakeStorage) -> UploadDocument:
    return UploadDocument(uow_factory(store), storage)


def _existing(store: InMemoryStore, active: bool) -> tuple[Document, Pipeline]:
    document = Document(
        file_name="law.pdf",
        file_path="/documents/law.pdf",
        size=4,
        sha256="sha",
        mime_type="application/pdf",
    )
    pipeline = Pipeline.start(document.id, PipelineStage.PARSING)
    if not active:
        pipeline.status = PipelineStatus.SUCCEEDED
    store.documents[document.id] = document
    store.pipelines[pipeline.id] = pipeline
    return document, pipeline


async def test_new_upload_creates_document_pipeline_and_event_in_one_commit() -> None:
    store = InMemoryStore()
    result = await _use_case(store, FakeStorage()).execute(
        BytesStream(b"data"), "law.pdf", "application/pdf"
    )

    assert store.commits == 1
    assert not result.duplicate
    assert result.document.status is PipelineStatus.IN_PROGRESS
    assert result.pipeline.stage is PipelineStage.UPLOADING
    [envelope] = store.outbox.values()
    assert envelope.event_type == FileReceivedEvent.event_type
    assert envelope.producer == "api"
    assert envelope.payload["staged_path"] == "/incoming/law.pdf"
    assert envelope.payload["pipeline_id"] == str(result.pipeline.id)


async def test_duplicate_with_active_pipeline_returns_it_without_new_work() -> None:
    store = InMemoryStore()
    document, active = _existing(store, active=True)
    storage = FakeStorage()

    result = await _use_case(store, storage).execute(
        BytesStream(b"data"), "copy.pdf", "application/pdf"
    )

    assert result.duplicate and result.pipeline.id == active.id
    assert store.outbox == {}
    assert storage.discarded == ["/incoming/copy.pdf"]


async def test_duplicate_without_active_pipeline_starts_one_from_stored_file() -> None:
    store = InMemoryStore()
    document, _ = _existing(store, active=False)

    result = await _use_case(store, FakeStorage()).execute(
        BytesStream(b"data"), "copy.pdf", "application/pdf"
    )

    assert result.duplicate and result.pipeline.is_active
    [envelope] = store.outbox.values()
    assert envelope.payload["staged_path"] == document.file_path


async def test_forced_duplicate_cancels_the_active_pipeline() -> None:
    store = InMemoryStore()
    _, active = _existing(store, active=True)

    result = await _use_case(store, FakeStorage()).execute(
        BytesStream(b"data"), "copy.pdf", "application/pdf", force_run=True
    )

    assert store.pipelines[active.id].status is PipelineStatus.CANCELLED
    assert result.pipeline.id != active.id and result.pipeline.is_active
    assert len(store.outbox) == 1


async def test_forced_duplicate_sends_the_run_trace_of_the_cancelled_run() -> None:
    store = InMemoryStore()
    _, active = _existing(store, active=True)
    tracer = RecordingTracer()

    await UploadDocument(uow_factory(store), FakeStorage(), tracer).execute(
        BytesStream(b"data"), "copy.pdf", "application/pdf", force_run=True
    )

    run = tracer.one_run(active.id)
    assert run.status == "CANCELLED" and run.error is None
    assert len(tracer.runs) == 1
