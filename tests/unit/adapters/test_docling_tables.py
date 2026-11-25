from types import SimpleNamespace

from app.adapters.outbound.parsing.docling.docling_tables import (
    clean_cell,
    contents_entries,
    table_to_text,
)

DOTS = "." * 60


def _table(label: str, rows: list[list[str]]) -> SimpleNamespace:
    cells = [
        SimpleNamespace(start_row_offset_idx=r, start_col_offset_idx=c, text=text)
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    return SimpleNamespace(label=label, data=SimpleNamespace(table_cells=cells))


def test_dot_leaders_are_removed_but_ordinary_punctuation_is_kept() -> None:
    assert clean_cell(f"ПРЕДИСЛОВИЕ {DOTS}") == "ПРЕДИСЛОВИЕ"
    assert clean_cell("Title . . . . . . 5") == "Title 5"
    assert clean_cell("Wait... what?") == "Wait... what?"


def test_contents_table_becomes_one_line_per_entry() -> None:
    table = _table(
        "document_index",
        [[f"ОТ ПЕРЕВОДЧИЦЫ {DOTS}", "1"], [f"ОТРЫВОК II из Книги {DOTS}", "7"]],
    )
    assert [(e.title, e.page) for e in contents_entries(table)] == [
        ("ОТ ПЕРЕВОДЧИЦЫ", 1),
        ("ОТРЫВОК II из Книги", 7),
    ]
    assert table_to_text(table) == "ОТ ПЕРЕВОДЧИЦЫ — p. 1\nОТРЫВОК II из Книги — p. 7"


def test_contents_entry_in_a_single_cell_is_split_on_its_leaders() -> None:
    [entry] = contents_entries(_table("document_index", [[f"Глава первая {DOTS} 12"]]))
    assert (entry.title, entry.page) == ("Глава первая", 12)


def test_contents_entry_without_a_page_keeps_its_title() -> None:
    [entry] = contents_entries(_table("document_index", [["Приложения"]]))
    assert (entry.title, entry.page) == ("Приложения", None)


def test_ordinary_table_is_markdown_with_a_header_row() -> None:
    table = _table("table", [["Имя", "Цена"], ["Чай", "5 | 6"], ["", ""], ["Кофе"]])
    assert table_to_text(table) == (
        "| Имя | Цена |\n| --- | --- |\n| Чай | 5 \\| 6 |\n| Кофе |  |"
    )


def test_table_without_cells_has_no_text() -> None:
    assert table_to_text(_table("table", [])) == ""
