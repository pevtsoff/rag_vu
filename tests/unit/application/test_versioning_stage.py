from app.application.dto.upload_override import UploadOverride
from app.application.use_cases.stages.version_stage_job import VersionStageJob
from app.domain.documents.document import Document
from app.domain.documents.parsed_node import ParsedNode
from app.domain.documents.versioning_override import VersioningOverride
from tests.unit.fakes.fake_ports import BytesStream, FakeEmbedder
from tests.unit.fakes.pipeline_harness import PipelineHarness

LAW = "Закон РФ от 07.02.1992 N 2300-1\n(ред. от 14.07.2022)\nО защите прав потребителей"
ARTICLES = [f"Статья {n}. Продавец обязан передать потребителю товар номер {n}." for n in range(40)]
OTHER = [f"Налоговый кодекс устанавливает налог номер {n} и порядок его уплаты." for n in range(40)]


async def _ingest(
    harness: PipelineHarness,
    sha: str,
    texts: list[str],
    override: UploadOverride | None = None,
    file_name: str = "law.pdf",
) -> Document:
    harness.storage.sha256 = sha
    harness.parser.nodes = [
        ParsedNode("Doc", text, ["Doc"], f"p{index:06d}", "section")
        for index, text in enumerate(texts)
    ]
    result = await harness.upload.execute(
        BytesStream(b"data"), file_name, "application/pdf", override=override
    )
    await harness.drain()
    return harness.store.documents[result.document.id]


def _refresh(harness: PipelineHarness, document: Document) -> Document:
    return harness.store.documents[document.id]


async def test_a_first_upload_is_version_one_of_its_own_cluster() -> None:
    harness = PipelineHarness()
    document = await _ingest(harness, "a", ARTICLES)
    assert (document.cluster_id, document.version, document.is_latest) == (document.id, 1, True)
    assert document.versioning == {"source": "new", "outcome": "new_document"}
    assert harness.store.fingerprints[document.id].avg_embedding is not None


async def test_an_edited_upload_becomes_the_next_latest_version() -> None:
    harness = PipelineHarness()
    first = await _ingest(harness, "a", ARTICLES)
    edited = [*ARTICLES[:20], "Статья 20. Новая редакция статьи.", *ARTICLES[21:]]
    second = await _ingest(harness, "b", edited)

    assert (second.cluster_id, second.version, second.is_latest) == (first.id, 2, True)
    assert not _refresh(harness, first).is_latest
    assert second.versioning["source"] == "fingerprint"
    assert 0.5 <= second.versioning["lexical_similarity"] < 0.99


async def test_the_same_text_in_another_file_is_marked_a_duplicate() -> None:
    harness = PipelineHarness()
    first = await _ingest(harness, "a", ARTICLES)
    copy = await _ingest(harness, "b", ARTICLES, file_name="law-copy.pdf")
    assert copy.is_duplicate and not copy.is_latest
    assert copy.doc_metadata["duplicate_of"] == str(first.id)
    assert _refresh(harness, first).is_latest


async def test_an_unrelated_document_starts_its_own_cluster() -> None:
    harness = PipelineHarness()
    first = await _ingest(harness, "a", ARTICLES)
    other = await _ingest(harness, "b", OTHER, file_name="tax.pdf")
    assert other.cluster_id == other.id != first.cluster_id
    assert other.is_latest and _refresh(harness, first).is_latest


async def test_the_legal_identifier_links_versions_and_is_stored() -> None:
    harness = PipelineHarness()
    first = await _ingest(harness, "a", [LAW, *ARTICLES])
    rewritten = await _ingest(harness, "b", [LAW.replace("14.07.2022", "01.03.2024"), *OTHER])

    assert rewritten.versioning["source"] == "identifier"
    assert (rewritten.cluster_id, rewritten.version) == (first.id, 2)
    assert rewritten.doc_metadata["identifier"] == "07.02.1992 N 2300-1"
    assert rewritten.doc_metadata["redaction"] == "01.03.2024"


async def test_force_upload_create_new_is_not_moved_by_the_versioning_stage() -> None:
    harness = PipelineHarness()
    first = await _ingest(harness, "a", ARTICLES)
    forced = await _ingest(
        harness, "b", ARTICLES[:-1], UploadOverride(VersioningOverride.CREATE_NEW)
    )
    assert (forced.cluster_id, forced.version, forced.is_latest) == (forced.id, 1, True)
    assert forced.file_name == "law_2.pdf"
    assert forced.versioning == {
        "source": "force_upload",
        "mode": "create_new",
        "original_file_name": "law.pdf",
    }
    assert harness.store.fingerprints[forced.id].minhash  # still fingerprinted for later uploads
    assert _refresh(harness, first).is_latest


async def test_vectors_of_another_size_version_by_identifier_only() -> None:
    harness = PipelineHarness(embedder=FakeEmbedder(2048))
    first = await _ingest(harness, "a", [LAW, *ARTICLES])
    assert harness.store.fingerprints[first.id].avg_embedding is None
    second = await _ingest(harness, "b", [LAW, *ARTICLES[:-2]])
    assert (second.cluster_id, second.versioning["source"]) == (first.id, "identifier")


async def test_rerunning_the_stage_keeps_an_assigned_version() -> None:
    harness = PipelineHarness()
    first = await _ingest(harness, "a", ARTICLES)
    second = await _ingest(harness, "b", [*ARTICLES[:-1], "Статья 39. Изменена."])
    job = VersionStageJob(harness.clock)
    assert await job._decide(harness.uow(), second, harness.store.fingerprints[second.id]) is None
    assert second.cluster_id == first.id
