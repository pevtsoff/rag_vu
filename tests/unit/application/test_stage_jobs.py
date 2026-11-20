from uuid import uuid4

import pytest

from app.application.errors import EmptyStageResultError, StorageError
from app.application.ports.chunker import Chunker
from app.application.use_cases.stages.chunk_stage_job import ChunkStageJob
from app.application.use_cases.stages.embed_stage_job import EmbedStageJob
from app.application.use_cases.stages.stage_context import StageContext
from app.application.use_cases.stages.upload_stage_job import UploadStageJob
from app.domain.documents.chunk import Chunk
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.document import Document
from app.domain.documents.node import Node
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.document_chunked_event import DocumentChunkedEvent
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.file_received_event import FileReceivedEvent
from tests.unit.fakes.fake_clock import FakeClock
from tests.unit.fakes.fake_ports import FakeEmbedder, FakeStorage
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import InMemoryUnitOfWork


class EmptyChunker(Chunker):
    async def chunk(self, nodes: list[Node], structure_path: str | None) -> list[ChunkDraft]:
        return []


def _document() -> Document:
    return Document(
        file_name="a.txt", file_path="/a.txt", size=4, sha256="sha", mime_type="text/plain"
    )


async def test_upload_stage_rejects_a_file_that_does_not_match_the_upload() -> None:
    document = _document()
    event = FileReceivedEvent(
        producer="api",
        document_id=document.id,
        pipeline_id=uuid4(),
        staged_path="/in",
        file_name="a.txt",
        size=4,
        sha256="other",
        mime_type="text/plain",
    )
    job = UploadStageJob(FakeClock(), FakeStorage(sha256="sha"))
    with pytest.raises(StorageError):
        await job.compute(StageContext(event, document))


async def test_chunk_stage_requires_parsed_nodes() -> None:
    store = InMemoryStore()
    document = _document()
    pipeline = Pipeline.start(document.id, PipelineStage.CHUNKING)
    store.documents[document.id], store.pipelines[pipeline.id] = document, pipeline
    event = DocumentParsedEvent(
        producer="t",
        document_id=document.id,
        pipeline_id=pipeline.id,
        structure_path=None,
        node_count=0,
    )
    async with InMemoryUnitOfWork(store) as uow:
        with pytest.raises(EmptyStageResultError, match="No parsed text nodes"):
            await ChunkStageJob(FakeClock(), EmptyChunker()).prepare(uow, event)


async def test_chunk_stage_rejects_an_empty_chunking_result() -> None:
    document = _document()
    node = Node(document_id=document.id, node_type="section", text="x")
    event = DocumentParsedEvent(
        producer="t",
        document_id=document.id,
        pipeline_id=uuid4(),
        structure_path=None,
        node_count=1,
    )
    with pytest.raises(EmptyStageResultError, match="No text chunks"):
        await ChunkStageJob(FakeClock(), EmptyChunker()).compute(
            StageContext(event, document, [node])
        )


async def test_embed_stage_batches_and_maps_vectors_to_chunk_ids() -> None:
    document = _document()
    chunks = [Chunk(uuid4(), uuid4(), i, f"text {i}") for i in range(5)]
    embedder = FakeEmbedder(dimensions=3)
    event = DocumentChunkedEvent(
        producer="t", document_id=document.id, pipeline_id=uuid4(), chunk_count=5
    )

    vectors = await EmbedStageJob(FakeClock(), embedder, batch_size=2).compute(
        StageContext(event, document, chunks)
    )

    assert [len(texts) for texts, _ in embedder.calls] == [2, 2, 1]
    assert list(vectors) == [chunk.id for chunk in chunks]


def test_embed_stage_requires_a_positive_batch_size() -> None:
    with pytest.raises(ValueError):
        EmbedStageJob(FakeClock(), FakeEmbedder(), batch_size=0)
