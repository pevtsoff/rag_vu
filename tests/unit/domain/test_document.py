from uuid import uuid4

from app.domain.documents.document import Document


def _document(**overrides: object) -> Document:
    return Document(
        file_name="law.pdf", file_path="/m/law.pdf", size=1, mime_type="pdf", **overrides
    )


def test_a_new_document_starts_its_own_cluster_as_the_latest_first_version() -> None:
    document = _document()
    assert document.cluster_id == document.id
    assert document.is_latest
    assert document.version == 1


def test_a_new_version_keeps_the_cluster_it_is_given() -> None:
    cluster_id = uuid4()
    document = _document(cluster_id=cluster_id, version=2)
    assert document.cluster_id == cluster_id
    assert document.id != cluster_id
