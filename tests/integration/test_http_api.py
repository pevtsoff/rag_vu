"""The real API container over PostgreSQL, called through ASGI."""

from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest

from app.adapters.inbound.http.app_factory import create_app
from app.bootstrap.api_container import ApiContainer
from app.bootstrap.infrastructure import Infrastructure
from app.domain.documents.parsed_node import ParsedNode


@pytest.fixture
async def client(infrastructure: Infrastructure) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(ApiContainer(infrastructure))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _upload(client: httpx.AsyncClient, **params: str) -> dict:
    files = {"file": ("law.pdf", b"%PDF data", "application/pdf")}
    response = await client.post("/api/v1/documents/upload", files=files, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_upload_is_durable_and_deduplicated(client: httpx.AsyncClient) -> None:
    first = await _upload(client)
    duplicate = await _upload(client)
    forced = await _upload(client, force_run="true")

    assert not first["duplicate"] and duplicate["duplicate"]
    assert duplicate["pipeline_id"] == first["pipeline_id"] != forced["pipeline_id"]
    pipelines = (await client.get(f"/api/v1/documents/{first['id']}/pipelines")).json()
    assert [p["status"] for p in pipelines] == ["IN_PROGRESS", "CANCELLED"]
    document = (await client.get(f"/api/v2/documents/{first['id']}")).json()
    assert document["status"] == "IN_PROGRESS"


async def test_rerun_requires_force_when_nothing_is_running(
    client: httpx.AsyncClient, infrastructure: Infrastructure
) -> None:
    uploaded = await _upload(client)
    url = f"/api/v1/documents/{uploaded['id']}/rerun/chunking"
    assert (await client.get(url)).json()["pipeline_id"] == uploaded["pipeline_id"]
    forced = (await client.get(url, params={"force_run": "true"})).json()
    assert forced["pipeline_id"] != uploaded["pipeline_id"]


async def test_node_html_is_served_from_the_database(
    client: httpx.AsyncClient, infrastructure: Infrastructure
) -> None:
    uploaded = await _upload(client)
    async with infrastructure.unit_of_work() as uow:
        document = await uow.documents.get(UUID(uploaded["id"]))
        await uow.nodes.replace_for_document(
            document.id,
            [ParsedNode("Статья 1", "Текст <b>", ["Закон", "Статья 1"], "s1.a1", "article")],
        )
        [node] = await uow.nodes.list_with_text(document.id)
        await uow.commit()
    response = await client.get(f"/api/v1/nodes/{node.id}/html")
    assert response.status_code == 200 and "Текст &lt;b&gt;" in response.text
