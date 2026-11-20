"""The FastAPI adapter wired to real use cases over in-memory fakes."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.app_factory import create_app
from app.adapters.outbound.rendering.jinja_node_renderer import JinjaNodeRenderer
from app.application.use_cases.documents.get_document import GetDocument
from app.application.use_cases.documents.list_document_pipelines import ListDocumentPipelines
from app.application.use_cases.documents.render_node import RenderNode
from app.application.use_cases.documents.rerun_pipeline import RerunPipeline
from app.application.use_cases.documents.search_documents import SearchDocuments
from app.application.use_cases.documents.upload_document import UploadDocument
from app.domain.documents.node import Node
from app.domain.retrieval.retrieved_match import RetrievedMatch
from tests.unit.fakes.fake_ports import FakeEmbedder, FakeRetriever, FakeStorage
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def client(store: InMemoryStore) -> TestClient:
    uow = uow_factory(store)
    match = RetrievedMatch(("node-1", "node-2"), "Passage", 0.5)
    services = SimpleNamespace(
        upload_document=UploadDocument(uow, FakeStorage()),
        rerun_pipeline=RerunPipeline(uow),
        get_document=GetDocument(uow),
        list_document_pipelines=ListDocumentPipelines(uow),
        render_node=RenderNode(uow, JinjaNodeRenderer()),
        search_documents=SearchDocuments(FakeEmbedder(2), FakeRetriever([match])),
    )
    return TestClient(create_app(services))


def _upload(client: TestClient, **params: object) -> dict:
    files = {"file": ("law.pdf", b"pdf data", "application/pdf")}
    response = client.post("/api/v1/documents/upload", files=files, params=params)
    assert response.status_code == 200
    return response.json()


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "healthy"}


def test_upload_then_read_document_and_pipelines(client: TestClient, store: InMemoryStore) -> None:
    uploaded = _upload(client)
    assert (uploaded["filename"], uploaded["status"], uploaded["duplicate"]) == (
        "law.pdf",
        "IN_PROGRESS",
        False,
    )
    assert store.outbox_types() == ["FileReceivedEvent"]

    document = client.get(f"/api/v1/documents/{uploaded['id']}").json()
    assert document["mime_type"] == "application/pdf"
    assert client.get(f"/api/v2/documents/{uploaded['id']}").status_code == 200
    [pipeline] = client.get(f"/api/v1/documents/{uploaded['id']}/pipelines").json()
    assert (pipeline["id"], pipeline["stage"], pipeline["embedded"]) == (
        uploaded["pipeline_id"],
        "uploading",
        False,
    )


def test_duplicate_upload_reuses_the_active_pipeline(client: TestClient) -> None:
    first = _upload(client)
    second = _upload(client)
    assert second["duplicate"] and second["pipeline_id"] == first["pipeline_id"]
    forced = _upload(client, force_run="true")
    assert forced["pipeline_id"] != first["pipeline_id"]


def test_rerun_endpoint(client: TestClient) -> None:
    uploaded = _upload(client)
    url = f"/api/v1/documents/{uploaded['id']}/rerun"
    assert client.get(f"{url}/parsing").json()["pipeline_id"] == uploaded["pipeline_id"]
    forced = client.get(f"{url}/embedding", params={"force_run": "true"}).json()
    assert forced["pipeline_id"] != uploaded["pipeline_id"] and forced["status"] == "IN_PROGRESS"
    assert client.get(f"{url}/upload").status_code == 422


def test_rerun_without_active_pipeline_is_409(client: TestClient, store: InMemoryStore) -> None:
    uploaded = _upload(client)
    for pipeline in store.pipelines.values():
        pipeline.cancel()
    response = client.get(f"/api/v1/documents/{uploaded['id']}/rerun/chunking")
    assert response.status_code == 409


@pytest.mark.parametrize("doc_id", ["not-a-uuid", str(uuid4())])
def test_unknown_documents_are_404(client: TestClient, doc_id: str) -> None:
    for path in (
        f"/api/v1/documents/{doc_id}",
        f"/api/v1/documents/{doc_id}/pipelines",
        f"/api/v1/documents/{doc_id}/rerun/parsing",
    ):
        response = client.get(path)
        assert (response.status_code, response.json()) == (404, {"detail": "Document not found"})


def test_node_html_is_escaped(client: TestClient, store: InMemoryStore) -> None:
    uploaded = _upload(client)
    node = Node(
        document_id=next(iter(store.documents)),
        node_type="article",
        title="Статья 10 <Право>",
        breadcrumbs=["Федеральный закон", "Статья 10"],
        text="Пункт <script>alert('x')</script>",
    )
    store.nodes[node.id] = node
    response = client.get(f"/api/v1/nodes/{node.id}/html")
    page = response.text
    assert response.status_code == 200 and "text/html" in response.headers["content-type"]
    assert '<html lang="ru">' in page and 'data-node-type="article"' in page
    assert "Статья 10 &lt;Право&gt;" in page and "<script>" not in page
    assert "Федеральный закон › Статья 10" in page
    assert uploaded["filename"] in page


def test_missing_node_is_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/nodes/{uuid4()}/html")
    assert (response.status_code, response.json()) == (404, {"detail": "Node not found"})


def test_search_returns_hits_and_validates_top_k(client: TestClient) -> None:
    for version in ("v1", "v2"):
        hits = client.post(
            f"/api/{version}/documents/search", json={"query": "q", "top_k": 1}
        ).json()
        assert hits == [
            {"id": "node-1", "content": "Passage", "score": 0.5, "node_ids": ["node-1", "node-2"]}
        ]
    assert (
        client.post("/api/v1/documents/search", json={"query": "q", "top_k": 0}).status_code == 422
    )
