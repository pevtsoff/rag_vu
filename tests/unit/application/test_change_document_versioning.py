from uuid import uuid4

import pytest

from app.application.errors import ClusterNotFoundError, DocumentNotFoundError
from app.application.use_cases.documents.change_document_versioning import (
    ChangeDocumentVersioning,
)
from app.domain.documents.document import Document
from app.domain.documents.versioning_change import VersioningChange
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory


def _version(store: InMemoryStore, cluster, version: int, latest: bool, **fields) -> Document:
    document = Document(
        file_name=f"v{version}.pdf",
        file_path="/d",
        size=1,
        mime_type="application/pdf",
        cluster_id=cluster,
        version=version,
        is_latest=latest,
        **fields,
    )
    store.documents[document.id] = document
    return document


def _cluster(store: InMemoryStore) -> tuple[Document, Document]:
    first = _version(store, None, 1, False)
    second = _version(store, first.id, 2, True)
    return first, second


async def test_splitting_the_latest_version_promotes_the_previous_one() -> None:
    store = InMemoryStore()
    first, second = _cluster(store)
    moved = await ChangeDocumentVersioning(uow_factory(store)).execute(
        second.id, VersioningChange.CREATE_NEW
    )
    assert (moved.cluster_id, moved.version, moved.is_latest) == (second.id, 1, True)
    assert store.documents[first.id].is_latest
    assert moved.versioning["source"] == "manual"


async def test_splitting_a_duplicate_makes_it_a_document_of_its_own() -> None:
    store = InMemoryStore()
    duplicate = _version(store, None, 1, False, doc_metadata={"duplicate_of": str(uuid4())})
    moved = await ChangeDocumentVersioning(uow_factory(store)).execute(
        duplicate.id, VersioningChange.CREATE_NEW
    )
    assert moved.is_latest and not moved.is_duplicate


async def test_joining_makes_the_document_the_latest_version_of_the_cluster() -> None:
    store = InMemoryStore()
    first, second = _cluster(store)
    other = _version(store, None, 1, True)
    moved = await ChangeDocumentVersioning(uow_factory(store)).execute(
        other.id, VersioningChange.JOIN, first.id
    )
    assert (moved.cluster_id, moved.version, moved.is_latest) == (first.id, 3, True)
    assert not store.documents[second.id].is_latest


async def test_unknown_documents_and_clusters_are_reported() -> None:
    store = InMemoryStore()
    other = _version(store, None, 1, True)
    use_case = ChangeDocumentVersioning(uow_factory(store))
    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(uuid4(), VersioningChange.CREATE_NEW)
    with pytest.raises(ClusterNotFoundError):
        await use_case.execute(other.id, VersioningChange.JOIN, uuid4())
