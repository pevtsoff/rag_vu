"""Creates law nodes with breadcrumbs and ltree paths."""

import re

from app.adapters.outbound.law_sources.pravo.law_cursor import LawCursor
from app.domain.documents.node_type import NodeType
from app.domain.documents.parsed_node import ParsedNode

MAX_OTHER_TEXT_LENGTH = 3000


class LawNodeFactory:
    def __init__(self, title: str) -> None:
        self._title = title

    def section_node(self, block: str, cursor: LawCursor) -> ParsedNode:
        breadcrumbs = self._breadcrumbs(cursor)
        path = ltree_path(cursor.section_number, None)
        title = breadcrumbs[-1] if breadcrumbs else "Раздел"
        return ParsedNode(title, block, breadcrumbs, path, NodeType.SECTION.value)

    def article_node(self, block: str, cursor: LawCursor) -> ParsedNode:
        breadcrumbs = self._breadcrumbs(cursor)
        path = ltree_path(cursor.section_number, cursor.article_number)
        title = breadcrumbs[-1] if breadcrumbs else "Статья"
        return ParsedNode(title, block, breadcrumbs, path, NodeType.ARTICLE.value)

    def part_node(self, number: str, content: str, cursor: LawCursor) -> ParsedNode:
        breadcrumbs = [*self._breadcrumbs(cursor), f"Пункт {number}"]
        path = ltree_path(cursor.section_number, cursor.article_number, number)
        return ParsedNode(
            f"Пункт {number}", content, breadcrumbs, path, NodeType.ARTICLE_PART.value
        )

    def other_node(self, block: str, node_type: str, index: int) -> ParsedNode:
        """A preamble or header block outside the section/article hierarchy."""
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if node_type == NodeType.PREAMBLE.value:
            title = "Преамбула"
        else:
            title = self._title or (lines[0] if lines else "Header")
        is_titled_header = node_type == NodeType.HEADER.value and self._title
        text = self._title if is_titled_header else block[:MAX_OTHER_TEXT_LENGTH]
        breadcrumbs = [self._title] if self._title else []
        return ParsedNode(title, text, breadcrumbs, f"n{index}", node_type)

    def _breadcrumbs(self, cursor: LawCursor) -> list[str]:
        breadcrumbs = [self._title] if self._title else []
        if cursor.section_number:
            breadcrumbs.append(_crumb("Раздел", cursor.section_number, cursor.section_name))
        if cursor.article_number:
            breadcrumbs.append(_crumb("Статья", cursor.article_number, cursor.article_name))
        return breadcrumbs


def ltree_path(section: str | None, article: str | None, part: str | None = None) -> str:
    labels = [
        f"{prefix}{re.sub(r'[^A-Za-z0-9_]', '_', str(number))}"
        for prefix, number in (("s", section), ("a", article), ("p", part))
        if number
    ]
    return ".".join(labels) if labels else "n1"


def _crumb(prefix: str, number: str, name: str) -> str:
    return f"{prefix} {number} — {name}" if name else f"{prefix} {number}"
