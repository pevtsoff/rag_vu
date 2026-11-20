import pytest
from sqlalchemy import text

from app.application.errors import ConcurrencyConflictError
from app.bootstrap.infrastructure import Infrastructure
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.document import Document
from app.domain.documents.parsed_node import ParsedNode
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus


def _document(sha: str = "sha") -> Document:
    return Document(
        file_name="law.pdf",
        file_path="/law.pdf",
        size=3,
        sha256=sha,
        mime_type="application/pdf",
        doc_metadata={"a": 1},
    )


async def test_documents_and_pipelines_round_trip(infrastructure: Infrastructure) -> None:
    document = _document()
    pipeline = Pipeline.start(document.id, PipelineStage.UPLOADING)
    async with infrastructure.unit_of_work() as uow:
        await uow.documents.add(document)
        await uow.pipelines.add(pipeline)
        await uow.commit()
    async with infrastructure.unit_of_work() as uow:
        stored = await uow.documents.get_by_sha256("sha", for_update=True)
        active = await uow.pipelines.get_active(document.id)
        assert stored.doc_metadata == {"a": 1} and stored.created_at is not None
        assert active.id == pipeline.id and active.stage is PipelineStage.UPLOADING
        active.complete(PipelineStage.UPLOADING, infrastructure.clock.now())
        await uow.pipelines.update(active)
        await uow.commit()
    async with infrastructure.unit_of_work() as uow:
        [reloaded] = await uow.pipelines.list_for_document(document.id)
    assert reloaded.uploaded and reloaded.stage is PipelineStage.PARSING


async def test_duplicate_content_is_a_concurrency_conflict(infrastructure: Infrastructure) -> None:
    async with infrastructure.unit_of_work() as uow:
        await uow.documents.add(_document())
        await uow.commit()
    with pytest.raises(ConcurrencyConflictError):
        async with infrastructure.unit_of_work() as uow:
            await uow.documents.add(_document())


async def test_only_one_pipeline_per_document_can_be_in_progress(
    infrastructure: Infrastructure,
) -> None:
    document = _document()
    async with infrastructure.unit_of_work() as uow:
        await uow.documents.add(document)
        await uow.pipelines.add(Pipeline.start(document.id, PipelineStage.UPLOADING))
        await uow.commit()
    with pytest.raises(ConcurrencyConflictError):
        async with infrastructure.unit_of_work() as uow:
            await uow.pipelines.add(Pipeline.start(document.id, PipelineStage.PARSING))
    async with infrastructure.unit_of_work() as uow:
        active = await uow.pipelines.get_active(document.id, for_update=True)
        active.cancel()
        await uow.pipelines.update(active)
        replacement = Pipeline.start(document.id, PipelineStage.PARSING, active)
        await uow.pipelines.add(replacement)
        await uow.commit()
    async with infrastructure.unit_of_work() as uow:
        assert (await uow.pipelines.get_latest(document.id)).id == replacement.id
        assert (await uow.pipelines.get(active.id)).status is PipelineStatus.CANCELLED


async def test_nodes_and_chunks_are_replaced_and_vectors_stored_by_size(
    infrastructure: Infrastructure,
) -> None:
    document = _document()
    nodes = [
        ParsedNode("B", "Second", ["Doc", "B"], "p000001.h2_b", "section"),
        ParsedNode("A", "First", ["Doc", "A"], "p000001.h1_a", "section"),
        ParsedNode("Empty", "  ", ["Doc"], "p000002", "section"),
    ]
    async with infrastructure.unit_of_work() as uow:
        await uow.documents.add(document)
        assert await uow.nodes.replace_for_document(document.id, nodes) == 3
        stored = await uow.nodes.list_with_text(document.id)
        assert [node.title for node in stored] == ["A", "B"]
        drafts = [ChunkDraft(node.id, 0, node.text) for node in stored]
        assert await uow.chunks.replace_for_document(document.id, drafts) == 2
        chunks = await uow.chunks.list_for_document(document.id)
        await uow.chunks.store_embeddings({chunk.id: [0.5] * 768 for chunk in chunks}, 768)
        await uow.commit()
    async with infrastructure.unit_of_work() as uow:
        assert await uow.chunks.count_for_document(document.id) == 2
        node, title = await uow.nodes.get_with_document_title(stored[0].id)
        assert (node.path, title) == ("p000001.h1_a", "law.pdf")
        await uow.nodes.replace_for_document(document.id, nodes[:1])
        assert await uow.chunks.count_for_document(document.id) == 0
        await uow.commit()
    assert await _vector_sizes(infrastructure) == []


async def _vector_sizes(infrastructure: Infrastructure) -> list[int]:
    async with infrastructure.session_factory() as session:
        result = await session.execute(text("SELECT vector_dims(embedding_small) FROM chunks"))
        return list(result.scalars())
