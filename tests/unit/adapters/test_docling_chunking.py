from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.adapters.outbound.chunking.docling_chunk_mapper import heading_map, make_docling_chunks
from app.adapters.outbound.chunking.docling_hybrid_chunker import DoclingHybridChunker
from app.adapters.outbound.chunking.hybrid_chunker_factory import create_hybrid_chunker
from app.adapters.outbound.chunking.table_text_serializer import (
    TableTextSerializer,
    TableTextSerializerProvider,
)
from app.domain.documents.node import Node


class FakeHybridChunker:
    def __init__(self, chunks: list[object], text: str = "Article 1\n\nLegal text") -> None:
        self._chunks, self._text = chunks, text
        self.documents: list[object] = []

    def chunk(self, dl_doc: object) -> list[object]:
        self.documents.append(dl_doc)
        return self._chunks

    def contextualize(self, chunk: object) -> str:
        return self._text


def test_docling_chunks_keep_contextualized_text() -> None:
    node_id, document = uuid4(), object()
    chunker = FakeHybridChunker([object()])
    chunks = make_docling_chunks(document, chunker, node_id)
    assert chunker.documents == [document]
    assert (chunks[0].node_id, chunks[0].text) == (node_id, "Article 1\n\nLegal text")


def test_docling_chunks_map_to_the_deepest_matching_heading_node() -> None:
    node_id, root_id = uuid4(), uuid4()
    chunk = SimpleNamespace(meta=SimpleNamespace(headings=["Overview", "Details", "Deeper"]))
    chunks = make_docling_chunks(
        object(), FakeHybridChunker([chunk]), {(): root_id, ("Overview", "Details"): node_id}
    )
    assert chunks[0].node_id == node_id


def test_heading_map_ignores_the_document_title_and_page_crumb() -> None:
    node = Node(document_id=uuid4(), node_type="section", breadcrumbs=["Law", "Page 2", "Раздел I"])
    assert heading_map([node]) == {("Раздел I",): node.id}


def test_chunker_factory_uses_tokenizer_and_budget() -> None:
    observed: dict[str, object] = {}

    class Tokenizer:
        def __init__(self, tokenizer: object, max_tokens: int) -> None:
            observed.update(tokenizer=tokenizer, max_tokens=max_tokens)

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(name: str) -> str:
            observed["model_name"] = name
            return "loaded-tokenizer"

    def hybrid_chunker(tokenizer: object, serializer_provider: object) -> object:
        observed["serializer_provider"] = serializer_provider
        return tokenizer

    create_hybrid_chunker(
        "Qwen/Qwen3-Embedding-0.6B", 384, hybrid_chunker, Tokenizer, AutoTokenizer
    )
    assert isinstance(observed.pop("serializer_provider"), TableTextSerializerProvider)
    assert observed == {
        "model_name": "Qwen/Qwen3-Embedding-0.6B",
        "tokenizer": "loaded-tokenizer",
        "max_tokens": 384,
    }


async def test_hybrid_chunker_falls_back_to_text_chunking_without_structure_file() -> None:
    node = Node(document_id=uuid4(), node_type="article", text="Статья 1. Текст.", path="s1.a1")
    chunker = DoclingHybridChunker(chunker_factory=lambda: (_ for _ in ()).throw(AssertionError))
    chunks = await chunker.chunk([node], None)
    assert [chunk.node_id for chunk in chunks] == [node.id]


async def test_hybrid_chunker_uses_structure_file_and_chunks_images_separately(
    tmp_path: Path,
) -> None:
    structure = tmp_path / "doc.docling.json"
    structure.write_text("{}")
    section = Node(
        document_id=uuid4(), node_type="section", text="S", breadcrumbs=["Doc"], path="p1"
    )
    image = Node(
        document_id=uuid4(),
        node_type="image",
        text="OCR text",
        breadcrumbs=["Doc", "Image 1"],
        path="img1",
    )
    fake = FakeHybridChunker([object(), object()], text="Section text")
    loaded: list[str] = []
    chunker = DoclingHybridChunker(
        lambda: fake, document_loader=lambda path: loaded.append(path) or "doc"
    )

    chunks = await chunker.chunk([section, image], str(structure))

    assert loaded == [str(structure)] and fake.documents == ["doc"]
    assert [(chunk.node_id, chunk.position) for chunk in chunks] == [
        (section.id, 0),
        (section.id, 1),
        (image.id, 0),
    ]


def _chunk(*headings: str) -> SimpleNamespace:
    return SimpleNamespace(meta=SimpleNamespace(headings=list(headings)))


def _nodes(*breadcrumbs: list[str]) -> list[Node]:
    document_id = uuid4()
    return [Node(document_id=document_id, node_type="section", breadcrumbs=b) for b in breadcrumbs]


def test_chunk_maps_to_a_nested_node_by_its_own_heading() -> None:
    chapter, verse = _nodes(["Doc", "Page 3", "ОТРЫВОК I"], ["Doc", "Page 4", "ОТРЫВОК I", "(7)"])
    mapping = heading_map([chapter, verse])
    assert mapping[("(7)",)] == verse.id
    chunks = make_docling_chunks(
        object(), FakeHybridChunker([_chunk("ПРЕДИСЛОВИЕ", "(7)")]), mapping
    )
    assert chunks[0].node_id == verse.id


def test_ambiguous_heading_is_not_aliased() -> None:
    first, second = _nodes(["Doc", "A", "* * *"], ["Doc", "B", "* * *"])
    assert ("* * *",) not in heading_map([first, second])


def test_chunk_under_a_part_of_a_merged_chapter_title_maps_to_that_chapter() -> None:
    title_page, preface, chapter, later = _nodes(
        ["Doc", "Page 1", "ГОЛОС БЕЗМОЛВИЯ ДВА ПУТИ СЕМЬ ВРАТ"],
        ["Doc", "Page 2", "ПРЕДИСЛОВИЕ"],
        ["Doc", "Page 7", "ОТРЫВОК II из Книги ДВА ПУТИ"],
        ["Doc", "Page 11", "ОТРЫВОК III из Книги СЕМЬ ВРАТ"],
    )
    mapping = heading_map([title_page, preface, chapter, later])
    # The title page also contains both phrases; document order says which node is meant.
    fake = FakeHybridChunker([_chunk("ПРЕДИСЛОВИЕ"), _chunk("ДВА ПУТИ"), _chunk("СЕМЬ ВРАТ")])
    assert [c.node_id for c in make_docling_chunks(object(), fake, mapping)] == [
        preface.id,
        chapter.id,
        later.id,
    ]


async def test_contents_nodes_are_not_chunked(tmp_path: Path) -> None:
    structure = tmp_path / "doc.docling.json"
    structure.write_text("{}")
    document_id = uuid4()
    contents = Node(
        document_id=document_id, node_type="contents", text="C", breadcrumbs=["Doc", "СОДЕРЖАНИЕ"]
    )
    body = Node(document_id=document_id, node_type="section", text="S", breadcrumbs=["Doc", "Body"])
    fake = FakeHybridChunker(
        [_chunk("СОДЕРЖАНИЕ"), _chunk("Body")], text="chunk text"
    )
    chunker = DoclingHybridChunker(lambda: fake, document_loader=lambda path: "doc")
    chunks = await chunker.chunk([contents, body], str(structure))
    assert [chunk.node_id for chunk in chunks] == [body.id]


def test_table_serializer_repeats_markdown_header_but_not_contents_lines() -> None:
    serializer = TableTextSerializer()
    header, body = serializer.get_header_and_body_lines(
        table_text="| a | b |\n| --- | --- |\n| 1 | 2 |"
    )
    assert (header, body) == (["| a | b |", "| --- | --- |"], ["| 1 | 2 |"])
    assert serializer.get_header_and_body_lines(table_text="A — p. 1\nB — p. 2") == (
        [],
        ["A — p. 1", "B — p. 2"],
    )
