"""Plain-text form of Docling tables, shared by node building and chunking.

Docling reports a table of contents as a ``document_index`` table whose cells carry dot
leaders ("Title ........ 12"); other tables are ordinary row/column grids.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.adapters.outbound.parsing.docling.docling_items import docling_label

DOCUMENT_INDEX_LABEL = "document_index"
TABLE_LABELS = frozenset({"table", DOCUMENT_INDEX_LABEL})

_LEADERS = re.compile(r"\s*(?:[.…]\s*){4,}")
_INLINE_PAGE = re.compile(r"^(?P<title>.*?\S)\s+(?P<page>\d{1,5})$")


@dataclass(frozen=True)
class ContentsEntry:
    title: str
    page: int | None = None

    def __str__(self) -> str:
        return f"{self.title} — p. {self.page}" if self.page is not None else self.title


def is_table(item: Any) -> bool:
    return docling_label(item) in TABLE_LABELS


def table_rows(item: Any) -> list[list[str]]:
    """The table's cells as rows of text (a spanning cell sits in its first position)."""
    cells = getattr(getattr(item, "data", None), "table_cells", None) or []
    grid: dict[int, dict[int, str]] = {}
    for cell in cells:
        row = getattr(cell, "start_row_offset_idx", None)
        column = getattr(cell, "start_col_offset_idx", None)
        if isinstance(row, int) and isinstance(column, int):
            grid.setdefault(row, {})[column] = str(getattr(cell, "text", "") or "")
    return [
        [columns.get(index, "") for index in range(max(columns) + 1)]
        for _, columns in sorted(grid.items())
    ]


def clean_cell(text: str) -> str:
    """Drop dot leaders and collapse whitespace."""
    return " ".join(_LEADERS.sub(" ", text).split())


def contents_entries(item: Any) -> list[ContentsEntry]:
    """The (title, page) rows of a table of contents."""
    entries = []
    for row in table_rows(item):
        cells = [clean_cell(cell) for cell in row]
        cells = [cell for cell in cells if cell]
        if not cells:
            continue
        if len(cells) > 1 and cells[-1].isdigit():
            entries.append(ContentsEntry(" ".join(cells[:-1]), int(cells[-1])))
            continue
        # One cell holding "Title ..... 12": the leaders are what separates title from page.
        raw = " ".join(row)
        inline = _INLINE_PAGE.match(" ".join(raw.split()))
        if inline and _LEADERS.search(raw):
            entries.append(ContentsEntry(clean_cell(inline["title"]), int(inline["page"])))
        else:
            entries.append(ContentsEntry(" ".join(cells)))
    return entries


def table_to_text(item: Any) -> str:
    """A table of contents as one "title — p. N" line per entry; any other table as Markdown."""
    if docling_label(item) == DOCUMENT_INDEX_LABEL:
        return "\n".join(str(entry) for entry in contents_entries(item))
    rows = [[_markdown_cell(cell) for cell in row] for row in table_rows(item)]
    rows = [row for row in rows if any(row)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [[*row, *[""] * (width - len(row))] for row in rows]
    lines = [_markdown_row(padded[0]), _markdown_row(["---"] * width)]
    lines.extend(_markdown_row(row) for row in padded[1:])
    return "\n".join(lines)


def _markdown_cell(text: str) -> str:
    return clean_cell(text).replace("|", "\\|")


def _markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"
