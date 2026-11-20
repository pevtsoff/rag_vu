from uuid import uuid4

from app.adapters.outbound.chunking.node_chunk_builder import (
    build_chunk_text,
    make_chunks,
    select_chunk_sources,
)
from app.adapters.outbound.chunking.text_chunker import TextChunker
from app.adapters.outbound.chunking.text_splitter import (
    MAX_CHUNK_SIZE,
    normalize_text,
    split_long_part,
)
from app.domain.documents.node import Node


def _node(
    text: str, node_type: str = "section", path: str = "p1", breadcrumbs: list[str] | None = None
) -> Node:
    return Node(
        document_id=uuid4(), node_type=node_type, text=text, path=path, breadcrumbs=breadcrumbs
    )


def test_normalize_text_preserves_paragraph_boundaries() -> None:
    assert normalize_text(" First   paragraph.\r\n\r\n  Second\tparagraph. ") == (
        "First paragraph.\n\nSecond paragraph."
    )


def test_split_long_part_keeps_short_text_and_splits_long_text() -> None:
    assert split_long_part("1. Short legal rule.") == ["1. Short legal rule."]
    long_text = " ".join("Слово." for _ in range(240))
    chunks = split_long_part(long_text)
    assert len(chunks) > 1
    assert all(len(chunk) <= MAX_CHUNK_SIZE for chunk in chunks)
    assert " ".join(chunks) == long_text


def test_unbroken_text_is_split_at_word_boundaries() -> None:
    text = " ".join("word" for _ in range(600))
    chunks = split_long_part(text)
    assert len(chunks) > 1 and " ".join(chunks) == text


def test_chunk_text_includes_breadcrumb_hierarchy() -> None:
    node = _node("x", breadcrumbs=["Закон", "Статья 1"])
    assert build_chunk_text(node, "  Правило.  ") == "Закон\nСтатья 1\n\nПравило."


def test_make_chunks_skips_empty_nodes_and_assigns_positions() -> None:
    node = _node("Короткий текст.", breadcrumbs=["Статья 1"])
    chunks = make_chunks([node, _node("  ")])
    assert [(chunk.node_id, chunk.position) for chunk in chunks] == [(node.id, 0)]
    assert "Статья 1" in chunks[0].text


def test_article_parts_replace_their_article_but_unpartitioned_articles_stay() -> None:
    nodes = [
        _node("Article 1 full text", "article", "s1.a1"),
        _node("1. Part one", "article_part", "s1.a1.p1"),
        _node("Article 2 full text", "article", "s1.a2"),
        _node("  ", "article", "s1.a3"),
    ]
    selected = select_chunk_sources(nodes)
    assert [(node.node_type, node.path) for node in selected] == [
        ("article_part", "s1.a1.p1"),
        ("article", "s1.a2"),
    ]


async def test_text_chunker_ignores_structure_path() -> None:
    node = _node("# Law\n\nGeneral document text.", breadcrumbs=["law.pdf"])
    chunks = await TextChunker().chunk([node], "/missing.json")
    assert len(chunks) == 1 and "General document text" in chunks[0].text
