"""Versioning against real PostgreSQL: partial unique indexes, JSONB and vector queries."""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.outbound.retrieval.candidate_queries import vector_candidates, version_rows
from app.application.dto.upload_override import UploadOverride
from app.application.use_cases.documents.upload_document import UploadDocument
from app.application.use_cases.stages.version_stage_job import VersionStageJob
from app.bootstrap.infrastructure import Infrastructure
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.document import Document
from app.domain.documents.parsed_node import ParsedNode
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.versioning_override import VersioningOverride
from app.domain.events.document_embedded_event import DocumentEmbeddedEvent
from tests.unit.fakes.fake_ports import BytesStream, FakeStorage

ARTICLES = [f"Статья {n}. Продавец обязан передать потребителю товар номер {n}." for n in range(40)]
EDITED = [*ARTICLES[:20], "Статья 20. Новая редакция статьи о товаре.", *ARTICLES[21:]]
VECTOR = [1.0] + [0.0] * 767


async def _embedded(infrastructure: Infrastructure, sha: str, texts: list[str]) -> Document:
    document = Document(
        file_name="law.pdf", file_path=f"/{sha}.pdf", size=1, sha256=sha, mime_type="pdf"
    )
    async with infrastructure.unit_of_work() as uow:
        await uow.documents.add(document)
        nodes = [ParsedNode("Doc", t, ["Doc"], f"p{i:06d}", "section") for i, t in enumerate(texts)]
        await uow.nodes.replace_for_document(document.id, nodes)
        stored = await uow.nodes.list_with_text(document.id)
        await uow.chunks.replace_for_document(
            document.id, [ChunkDraft(node.id, 0, node.text or "") for node in stored]
        )
        chunks = await uow.chunks.list_for_document(document.id)
        await uow.chunks.store_embeddings({chunk.id: VECTOR for chunk in chunks}, 768)
        await uow.commit()
    return document


async def _version(infrastructure: Infrastructure, document: Document) -> Document:
    """Run the versioning stage's prepare/compute/persist steps directly."""
    pipeline = Pipeline.start(document.id, PipelineStage.VERSIONING)
    async with infrastructure.unit_of_work() as uow:
        await uow.pipelines.add(pipeline)
        await uow.commit()
    event = DocumentEmbeddedEvent(
        producer="test",
        document_id=document.id,
        pipeline_id=pipeline.id,
        chunk_count=1,
        dimensions=768,
    )
    job = VersionStageJob(infrastructure.clock)
    async with infrastructure.unit_of_work() as uow:
        context = await job.prepare(uow, event)
    result = await job.compute(context)
    async with infrastructure.unit_of_work() as uow:
        persisted = await job.persist(uow, context, result)
        await uow.commit()
    return persisted.document


def _rows(engine: Engine, sql: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


async def test_an_edited_upload_becomes_version_two_in_postgres(
    infrastructure: Infrastructure, sync_engine: Engine
) -> None:
    first = await _version(infrastructure, await _embedded(infrastructure, "a", ARTICLES))
    second = await _version(infrastructure, await _embedded(infrastructure, "b", EDITED))

    assert (second.cluster_id, second.version, second.is_latest) == (first.id, 2, True)
    assert _rows(
        sync_engine,
        "SELECT version, is_latest, cardinality(minhash_sig), avg_embedding IS NOT NULL "
        "FROM documents ORDER BY version",
    ) == [(1, False, 128, True), (2, True, 128, True)]
    async with infrastructure.unit_of_work() as uow:
        nearest = await uow.documents.nearest_latest(VECTOR, 0.08, 5, first.id)
    assert nearest == []  # the only latest version is in the excluded cluster


async def test_retrieval_filters_old_versions_and_duplicates(
    infrastructure: Infrastructure,
) -> None:
    first = await _version(infrastructure, await _embedded(infrastructure, "a", ARTICLES))
    second = await _version(infrastructure, await _embedded(infrastructure, "b", EDITED))
    copy = await _version(infrastructure, await _embedded(infrastructure, "c", EDITED))
    assert copy.is_duplicate

    async with infrastructure.session_factory() as session:
        latest = (await session.execute(vector_candidates("embedding_small", VECTOR, 200))).all()
        every = (
            await session.execute(vector_candidates("embedding_small", VECTOR, 200, False))
        ).all()
        versions = (await session.execute(version_rows([str(every[0][0])]))).all()

    assert len(latest) == len(EDITED) and len(every) == len(ARTICLES) + len(EDITED)
    assert {row[1] for row in versions} <= {first.id, second.id}
    assert versions[0][2] == first.id  # cluster id


async def test_replace_latest_reuses_the_version_number(
    infrastructure: Infrastructure, sync_engine: Engine
) -> None:
    first = await _version(infrastructure, await _embedded(infrastructure, "a", ARTICLES))
    upload = UploadDocument(
        infrastructure.unit_of_work, FakeStorage(sha256="new"), clock=infrastructure.clock
    )
    result = await upload.execute(
        BytesStream(b"x"),
        "law.pdf",
        "application/pdf",
        override=UploadOverride(VersioningOverride.REPLACE_LATEST),
    )

    assert (result.document.cluster_id, result.document.version) == (first.id, 1)
    assert _rows(
        sync_engine,
        "SELECT sha256, is_latest, deleted_at IS NOT NULL FROM documents ORDER BY created_at",
    ) == [(None, False, True), ("new", True, False)]


async def test_create_new_gets_a_free_file_name(infrastructure: Infrastructure) -> None:
    await _version(infrastructure, await _embedded(infrastructure, "a", ARTICLES))
    upload = UploadDocument(
        infrastructure.unit_of_work, FakeStorage(sha256="new"), clock=infrastructure.clock
    )
    result = await upload.execute(
        BytesStream(b"x"),
        "law.pdf",
        "application/pdf",
        override=UploadOverride(VersioningOverride.CREATE_NEW),
    )
    assert result.document.file_name == "law_2.pdf"
