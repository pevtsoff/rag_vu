from uuid import uuid4

import pytest

from app.application.dto.upload_override import UploadOverride
from app.application.errors import (
    AmbiguousVersioningTargetError,
    DuplicateContentError,
    VersioningTargetNotFoundError,
)
from app.application.use_cases.documents.upload_document import UploadDocument
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus
from app.domain.documents.versioning_override import VersioningOverride
from tests.unit.fakes.fake_clock import FakeClock
from tests.unit.fakes.fake_ports import BytesStream, FakeStorage
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory

REPLACE = UploadOverride(VersioningOverride.REPLACE_LATEST)
CREATE = UploadOverride(VersioningOverride.CREATE_NEW)


def _stored(store: InMemoryStore, sha: str = "old", version: int = 2, **fields) -> Document:
    document = Document(
        file_name="law.pdf",
        file_path="/documents/law.pdf",
        size=4,
        sha256=sha,
        mime_type="application/pdf",
        version=version,
        **fields,
    )
    store.documents[document.id] = document
    return document


async def _upload(
    store: InMemoryStore, override: UploadOverride, sha: str = "new", name: str = "law.pdf"
):
    storage = FakeStorage(sha256=sha)
    use_case = UploadDocument(uow_factory(store), storage, clock=FakeClock())
    return await use_case.execute(
        BytesStream(b"x"), name, "application/pdf", override=override
    ), storage


async def test_replace_latest_takes_the_place_of_the_latest_version() -> None:
    store = InMemoryStore()
    old = _stored(store, cluster_id=uuid4())
    running = Pipeline.start(old.id, PipelineStage.PARSING)
    store.pipelines[running.id] = running

    result, _ = await _upload(store, REPLACE)

    new, replaced = result.document, store.documents[old.id]
    assert (new.cluster_id, new.version, new.is_latest) == (old.cluster_id, 2, True)
    assert replaced.deleted_at is not None and not replaced.is_latest
    assert replaced.sha256 is None and replaced.doc_metadata["replaced_sha256"] == "old"
    assert store.pipelines[running.id].status is PipelineStatus.CANCELLED
    assert new.versioning == {
        "source": "force_upload",
        "mode": "replace_latest",
        "replaced_document_id": str(old.id),
    }


async def test_create_new_starts_a_separate_cluster_and_leaves_the_old_one() -> None:
    store = InMemoryStore()
    old = _stored(store)
    result, _ = await _upload(store, CREATE)
    assert (result.document.cluster_id, result.document.version) == (result.document.id, 1)
    assert store.documents[old.id].is_latest
    assert result.document.versioning["mode"] == "create_new"


async def test_create_new_renames_the_upload_to_a_free_file_name() -> None:
    store = InMemoryStore()
    _stored(store)
    first, _ = await _upload(store, CREATE, sha="n1")
    second, _ = await _upload(store, CREATE, sha="n2")

    assert (first.document.file_name, second.document.file_name) == ("law_2.pdf", "law_3.pdf")
    assert first.document.versioning["original_file_name"] == "law.pdf"
    [envelope] = [
        e for e in store.outbox.values() if e.payload["document_id"] == str(first.document.id)
    ]
    assert envelope.payload["file_name"] == "law_2.pdf"  # stored under the new name


async def test_an_unknown_file_name_is_rejected_and_the_staged_file_discarded() -> None:
    store = InMemoryStore()
    with pytest.raises(VersioningTargetNotFoundError):
        await _upload(store, REPLACE, name="missing.pdf")
    assert store.documents == {} and store.commits == 0


async def test_a_name_shared_by_two_clusters_needs_cluster_id() -> None:
    store = InMemoryStore()
    first, second = _stored(store, sha="a"), _stored(store, sha="b")
    with pytest.raises(AmbiguousVersioningTargetError) as error:
        await _upload(store, REPLACE)
    assert set(error.value.cluster_ids) == {str(first.cluster_id), str(second.cluster_id)}

    picked = UploadOverride(VersioningOverride.REPLACE_LATEST, second.cluster_id)
    result, _ = await _upload(store, picked)
    assert result.document.cluster_id == second.cluster_id
    assert store.documents[first.id].is_latest


async def test_create_new_with_identical_content_is_a_conflict() -> None:
    store = InMemoryStore()
    _stored(store, sha="same")
    with pytest.raises(DuplicateContentError):
        await _upload(store, CREATE, sha="same")


async def test_replace_latest_with_the_identical_file_is_a_no_op() -> None:
    store = InMemoryStore()
    old = _stored(store, sha="same")
    result, storage = await _upload(store, REPLACE, sha="same")
    assert result.duplicate and result.document.id == old.id
    assert store.documents[old.id].deleted_at is None
    assert storage.discarded == ["/incoming/law.pdf"]
