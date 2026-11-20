"""pgvector similarity and pg_textsearch BM25 retrieval on real data."""

from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.adapters.outbound.retrieval.sqlalchemy_hybrid_retriever import SqlAlchemyHybridRetriever
from app.bootstrap.infrastructure import Infrastructure
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.document import Document
from app.domain.documents.parsed_node import ParsedNode

NODES = [
    ParsedNode(
        "Статья 1 — Воинская обязанность",
        "Статья 1. Воинская обязанность граждан включает воинский учет.",
        ["Закон", "Статья 1 — Воинская обязанность"],
        "s1.a1",
        "article",
    ),
    ParsedNode(
        "Статья 2 — Персональные данные",
        "Статья 2. Обработка персональных данных допускается с согласия.",
        ["Закон", "Статья 2 — Персональные данные"],
        "s1.a2",
        "article",
    ),
    ParsedNode(
        "Статья 48 — Срок службы",
        "Статья 48. Срок военной службы устанавливается законом.",
        ["Закон", "Статья 48 — Срок службы"],
        "s1.a48",
        "article",
    ),
]


def _vector(axis: int) -> list[float]:
    vector = [0.0] * 768
    vector[axis] = 1.0
    return vector


async def _index(infrastructure: Infrastructure) -> None:
    document = Document(
        file_name="Закон", file_path="https://law", size=1, sha256="law", mime_type="text/html"
    )
    async with infrastructure.unit_of_work() as uow:
        await uow.documents.add(document)
        await uow.nodes.replace_for_document(document.id, NODES)
        nodes = await uow.nodes.list_with_text(document.id)
        await uow.chunks.replace_for_document(
            document.id, [ChunkDraft(n.id, 0, n.text) for n in nodes]
        )
        chunks = await uow.chunks.list_for_document(document.id)
        await uow.chunks.store_embeddings({c.id: _vector(i) for i, c in enumerate(chunks)}, 768)
        await uow.commit()


def _retriever(infrastructure: Infrastructure) -> SqlAlchemyHybridRetriever:
    return SqlAlchemyHybridRetriever(infrastructure.session_factory, RetrievalLimits(10, 10, 60))


async def test_vector_and_bm25_agree_on_the_best_node(infrastructure: Infrastructure) -> None:
    await _index(infrastructure)
    matches = await _retriever(infrastructure).retrieve(_vector(0), "воинская обязанность")
    assert "Воинская обязанность" in matches[0].text
    assert matches[0].score > matches[-1].score
    assert "Документ: Закон" in matches[0].text


async def test_article_numbers_are_found_exactly(infrastructure: Infrastructure) -> None:
    await _index(infrastructure)
    matches = await _retriever(infrastructure).retrieve(_vector(1), "Что говорит статья 48?")
    assert "Статья 48" in matches[0].text
