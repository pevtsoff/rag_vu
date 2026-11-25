from pathlib import Path
from types import SimpleNamespace

import pytest

from app.adapters.outbound.parsing.docling.docling_document_parser import DoclingDocumentParser
from app.adapters.outbound.parsing.docling.docling_image_extractor import DoclingImageExtractor
from app.adapters.outbound.parsing.docling.docling_node_builder import DoclingNodeBuilder
from app.adapters.outbound.parsing.image_text_recognizer import ImageTextRecognizer
from app.domain.documents.node_type import NodeType


class FixedRecognizer(ImageTextRecognizer):
    def recognize(self, png_bytes: bytes) -> str:
        return "recognized"


def _item(label: str, text: str, parent: object = None, page: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        label=label,
        text=text,
        self_ref=f"#/{text}",
        parent=SimpleNamespace(resolve=lambda doc, value=parent: value) if parent else None,
        prov=[SimpleNamespace(page_no=page)],
    )


def _heading(text: str, page: int = 2, level: int = 1) -> SimpleNamespace:
    item = _item("section_header", text, page=page)
    item.level = level
    return item


def _contents(*entries: tuple[str, int]) -> SimpleNamespace:
    cells = [
        SimpleNamespace(start_row_offset_idx=row, start_col_offset_idx=column, text=text)
        for row, (title, page) in enumerate(entries)
        for column, text in enumerate((f"{title} ........................", str(page)))
    ]
    item = _item("document_index", "", page=1)
    item.data = SimpleNamespace(table_cells=cells)
    return item


def _document(items: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(iterate_items=lambda **_: iter((item, 0) for item in items))


def test_native_headings_build_page_section_hierarchy() -> None:
    section = _item("section_header", "Раздел I")
    article = _item("section_header", "Статья 1", parent=section)
    document = _document(
        [
            section,
            _item("text", "Section body", section),
            article,
            _item("text", "Article body", article),
        ]
    )
    nodes = DoclingNodeBuilder().build(document, "Law")
    assert nodes[0].breadcrumbs == ["Law", "Page 2", "Раздел I"]
    assert nodes[0].path == "p000002.h1_razdel_i"
    assert nodes[0].text == "Раздел I\n\nSection body"
    assert nodes[1].breadcrumbs == ["Law", "Page 2", "Раздел I", "Статья 1"]
    assert nodes[1].path == "p000002.h1_razdel_i.h1_statya_1"


def test_heading_levels_nest_sections_without_explicit_parents() -> None:
    chapter = _item("section_header", "Chapter")
    chapter.level = 1
    part = _item("section_header", "Part")
    part.level = 2
    nodes = DoclingNodeBuilder().build(_document([chapter, part, _item("text", "Body")]), "Doc")
    assert nodes[1].breadcrumbs == ["Doc", "Page 2", "Chapter", "Part"]
    assert nodes[1].text.endswith("Body")


def test_plain_text_legal_heading_is_not_promoted_to_a_section() -> None:
    article = _item("text", "Статья 1. Воинская обязанность")
    body = _item("text", "Воинская обязанность граждан предусматривает:", parent=article)
    nodes = DoclingNodeBuilder().build(_document([article, body]), "Law")
    assert [node.node_type for node in nodes] == ["preamble"]
    assert article.text in nodes[0].text


def _book() -> SimpleNamespace:
    return _document(
        [
            _heading("СОДЕРЖАНИЕ", page=1),
            _contents(("ПРЕДИСЛОВИЕ", 2), ("ОТРЫВОК II из Книги ДВА ПУТИ", 7), ("ПРИМЕЧАНИЯ", 15)),
            _heading("ПРЕДИСЛОВИЕ", page=2),
            _item("text", "Preface body", page=2),
            _heading("(7)", page=4),
            _item("text", "Verse seven", page=4),
            _heading("ОТРЫВОК II", page=7),
            _heading("из Книги", page=7, level=2),
            _heading("ДВА ПУТИ", page=7),
            _item("text", "Two paths body", page=7),
            _heading("(16)", page=9),
            _item("text", "Verse sixteen", page=9),
            _heading("ПРИМЕЧАНИЯ", page=15, level=3),
            _heading("II", page=18, level=4),
        ]
    )


def test_contents_entries_become_top_level_chapters_and_other_headings_nest_in_them() -> None:
    nodes = {node.breadcrumbs[-1]: node for node in DoclingNodeBuilder().build(_book(), "Book")}
    assert nodes["(7)"].breadcrumbs == ["Book", "Page 4", "ПРЕДИСЛОВИЕ", "(7)"]
    assert nodes["(7)"].text.endswith("Verse seven")
    assert nodes["(16)"].breadcrumbs[2:] == ["ОТРЫВОК II из Книги ДВА ПУТИ", "(16)"]
    assert nodes["II"].breadcrumbs[2:] == ["ПРИМЕЧАНИЯ", "II"]


def test_a_chapter_title_split_over_headings_is_one_node() -> None:
    nodes = DoclingNodeBuilder().build(_book(), "Book")
    titles = [node.breadcrumbs[-1] for node in nodes]
    assert "ОТРЫВОК II из Книги ДВА ПУТИ" in titles
    assert not {"ОТРЫВОК II", "из Книги", "ДВА ПУТИ"} & set(titles)
    chapter = next(node for node in nodes if node.title == "ОТРЫВОК II из Книги ДВА ПУТИ")
    assert chapter.text.endswith("Two paths body")


def test_contents_node_lists_the_entries_and_is_not_searchable() -> None:
    nodes = DoclingNodeBuilder().build(_book(), "Book")
    contents = next(node for node in nodes if node.node_type == "contents")
    assert contents.breadcrumbs == ["Book", "Page 1", "СОДЕРЖАНИЕ"]
    assert contents.text == (
        "СОДЕРЖАНИЕ\n\nПРЕДИСЛОВИЕ — p. 2\nОТРЫВОК II из Книги ДВА ПУТИ — p. 7\nПРИМЕЧАНИЯ — p. 15"
    )
    assert NodeType.CONTENTS not in NodeType.retrievable()


def test_headings_keep_their_docling_levels_without_a_contents_table() -> None:
    document = _document([_heading("A"), _heading("B", level=2), _heading("C")])
    nodes = DoclingNodeBuilder().build(document, "Doc")
    assert [node.breadcrumbs[2:] for node in nodes] == [["A"], ["A", "B"], ["C"]]


def test_tables_join_the_section_they_follow_as_markdown() -> None:
    table = _item("table", "", page=2)
    table.data = SimpleNamespace(
        table_cells=[
            SimpleNamespace(start_row_offset_idx=r, start_col_offset_idx=c, text=t)
            for r, row in enumerate([["Имя", "Цена"], ["Чай", "5"]])
            for c, t in enumerate(row)
        ]
    )
    nodes = DoclingNodeBuilder().build(_document([_heading("Меню"), table]), "Doc")
    assert nodes[0].text == "Меню\n\n| Имя | Цена |\n| --- | --- |\n| Чай | 5 |"


def test_empty_document_gets_a_header_node() -> None:
    [node] = DoclingNodeBuilder().build(_document([]), "Empty")
    assert (node.node_type, node.path, node.breadcrumbs) == ("header", "n1", ["Empty"])


def test_pictures_are_saved_and_ocr_text_becomes_an_image_node(tmp_path: Path) -> None:
    class Image:
        def save(self, target: object, format: str | None = None) -> None:  # noqa: A002
            if isinstance(target, Path):
                target.write_bytes(b"png")
            else:
                target.write(b"png")

    picture = _item("picture", "", page=3)
    picture.get_image = lambda document: Image()
    [node] = DoclingImageExtractor(FixedRecognizer()).extract(_document([picture]), tmp_path, "Doc")
    assert (tmp_path / "images" / "image_0001.png").is_file()
    assert (node.node_type, node.text, node.breadcrumbs) == (
        "image",
        "recognized",
        ["Doc", "Page 3", "Image 1"],
    )


async def test_parser_converts_saves_structure_and_builds_nodes(tmp_path: Path) -> None:
    source = tmp_path / "law.pdf"
    source.write_bytes(b"fixture")
    saved: list[str] = []
    document = SimpleNamespace(
        name="Law title",
        iterate_items=lambda **_: iter([(_item("text", "Body"), 0)]),
        save_as_json=lambda path, image_mode: saved.append(path),
    )
    converter = SimpleNamespace(convert=lambda path: SimpleNamespace(document=document))
    parser = DoclingDocumentParser(
        lambda: converter, DoclingNodeBuilder(), DoclingImageExtractor(FixedRecognizer())
    )

    parsed = await parser.parse(str(source), "fallback")

    assert parsed.title == "Law title"
    assert parsed.structure_path == f"{source}.docling.json" and saved == [parsed.structure_path]
    assert [node.text for node in parsed.nodes] == ["Body"]


async def test_parser_rejects_missing_input() -> None:
    parser = DoclingDocumentParser(
        object, DoclingNodeBuilder(), DoclingImageExtractor(FixedRecognizer())
    )
    with pytest.raises(FileNotFoundError, match="does not exist"):
        await parser.parse("/missing/input.pdf", "x")
