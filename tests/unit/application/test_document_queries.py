from uuid import uuid4

import pytest

from app.application.errors import DocumentNotFoundError, NodeNotFoundError
from app.application.ports.node_renderer import NodeRenderer
from app.application.use_cases.documents.get_document import GetDocument
from app.application.use_cases.documents.list_document_pipelines import ListDocumentPipelines
from app.application.use_cases.documents.render_node import RenderNode
from app.application.use_cases.documents.search_documents import SearchDocuments
from app.domain.documents.document import Document
from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.documents.node import Node
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.retrieval.retrieved_match import RetrievedMatch
from tests.unit.fakes.fake_ports import FakeEmbedder, FakeRetriever
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory


class TitleRenderer(NodeRenderer):
    def render(self, node: Node, document_title: str) -> str:
        return f"{document_title}:{node.title}"


def _store_with_document() -> tuple[InMemoryStore, Document]:
    store = InMemoryStore()
    document = Document(
        file_name="law.pdf", file_path="/law.pdf", size=1, mime_type="application/pdf"
    )
    store.documents[document.id] = document
    return store, document


async def test_get_document_and_missing_document() -> None:
    store, document = _store_with_document()
    assert (await GetDocument(uow_factory(store)).execute(document.id)).id == document.id
    with pytest.raises(DocumentNotFoundError):
        await GetDocument(uow_factory(store)).execute(uuid4())


async def test_list_pipelines_newest_first_and_empty_list() -> None:
    store, document = _store_with_document()
    use_case = ListDocumentPipelines(uow_factory(store))
    assert await use_case.execute(document.id) == []
    first, second = (Pipeline.start(document.id, PipelineStage.PARSING) for _ in range(2))
    first.cancel()
    store.pipelines.update({first.id: first, second.id: second})
    assert [p.id for p in await use_case.execute(document.id)] == [second.id, first.id]
    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(uuid4())


@pytest.mark.parametrize("node_type", ["article", "article_part", "section", "preamble", "header"])
async def test_render_node_renders_retrievable_types(node_type: str) -> None:
    store, document = _store_with_document()
    node = Node(document_id=document.id, node_type=node_type, title="Статья 1")
    store.nodes[node.id] = node
    page = await RenderNode(uow_factory(store), TitleRenderer()).execute(node.id)
    assert page == "law.pdf:Статья 1"


@pytest.mark.parametrize("node_type", ["image", "footer"])
async def test_render_node_hides_other_types_and_missing_nodes(node_type: str) -> None:
    store, document = _store_with_document()
    node = Node(document_id=document.id, node_type=node_type)
    store.nodes[node.id] = node
    use_case = RenderNode(uow_factory(store), TitleRenderer())
    with pytest.raises(NodeNotFoundError):
        await use_case.execute(node.id)
    with pytest.raises(NodeNotFoundError):
        await use_case.execute(uuid4())


async def test_search_embeds_the_query_and_limits_results() -> None:
    matches = [RetrievedMatch((str(uuid4()),), f"Passage {i}", 1.0 / (i + 1)) for i in range(5)]
    embedder, retriever = FakeEmbedder(dimensions=2), FakeRetriever(matches)
    found = await SearchDocuments(embedder, retriever).execute("question", top_k=2)
    assert found == matches[:2]
    assert embedder.calls == [(["question"], EmbeddingTask.QUERY)]
    assert retriever.calls[0][1] == "question"
