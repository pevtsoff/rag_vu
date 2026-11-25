"""Builds searchable nodes from Docling's parent-child item hierarchy."""

from typing import Any

from app.adapters.outbound.parsing.docling.docling_items import (
    docling_label,
    heading_level,
    item_ref,
    item_text,
    page_label,
    page_number,
)
from app.adapters.outbound.parsing.docling.docling_tables import (
    DOCUMENT_INDEX_LABEL,
    contents_entries,
    is_table,
    table_to_text,
)
from app.adapters.outbound.parsing.docling.docling_tree_state import ChapterTitle, DoclingTreeState
from app.adapters.outbound.parsing.docling.section_entry import SectionEntry
from app.adapters.outbound.parsing.ltree_label import ltree_label
from app.domain.documents.node_type import NodeType
from app.domain.documents.parsed_node import ParsedNode

SECTION_HEADER_LABEL = "section_header"
MIN_PARTIAL_TITLE_KEY = 4


class DoclingNodeBuilder:
    """Section headers become section nodes; other text joins the nearest section.

    Text before the first heading of a page becomes that page's preamble node.

    Docling's heading levels are guesses (on a scanned book, verse numbers come out as
    top-level headings), so when the document has a table of contents its entries decide the
    structure: each entry is a top-level chapter (a title split over several headings is
    merged), and every other heading after it nests directly under that chapter.
    """

    def build(self, document: Any, title: str) -> list[ParsedNode]:
        state = DoclingTreeState(title=title, chapters=_chapter_titles(document))
        for item, _ in document.iterate_items(with_groups=False):
            self._visit(item, document, state)
        state.nodes[:0] = self._preamble_nodes(state)
        if not state.nodes:
            state.nodes.append(ParsedNode(title, "", [title], "n1", NodeType.HEADER.value))
        return state.nodes

    def _visit(self, item: Any, document: Any, state: DoclingTreeState) -> None:
        label = docling_label(item)
        if is_table(item):
            self._add_table(item, document, state)
            return
        text = item_text(item)
        if not text:
            return
        if label != SECTION_HEADER_LABEL:
            state.pending_chapter = None
        ancestors = self._explicit_ancestors(item, document, state)
        if label == SECTION_HEADER_LABEL:
            if self._chapter_heading(item, text, state):
                return
            self._add_section(item, text, self._heading_ancestors(item, ancestors, state), state)
        elif ancestors:
            ancestors[-1].node.text += "\n\n" + text
        elif state.heading_stack:
            state.heading_stack[-1].node.text += "\n\n" + text
        else:
            state.preambles.setdefault(page_number(item), []).append(text)

    def _add_section(
        self, item: Any, text: str, ancestors: list[SectionEntry], state: DoclingTreeState
    ) -> None:
        page = page_number(item)
        parent_key = ancestors[-1].key if ancestors else page_label(page)
        ordinal = state.sibling_counts.get(parent_key, 0) + 1
        state.sibling_counts[parent_key] = ordinal
        node = _section_node(text, state.title, page, ancestors, ordinal)
        state.nodes.append(node)
        entry = SectionEntry(text, f"{parent_key}.h{ordinal}", ordinal, node, heading_level(item))
        state.sections[item_ref(item)] = entry
        state.heading_stack.append(entry)

    def _chapter_heading(self, item: Any, text: str, state: DoclingTreeState) -> bool:
        """Consume a heading that opens, or continues the title of, a contents chapter."""
        key = title_key(text)
        if not state.chapters or not key:
            return False
        if state.pending_chapter is not None:
            full, merged = state.pending_chapter
            merged += key
            if full.startswith(merged):
                state.pending_chapter = None if merged == full else (full, merged)
                return True
            state.pending_chapter = None
        for index in range(state.next_chapter, len(state.chapters)):
            chapter = state.chapters[index]
            complete = chapter.key == key
            if complete or (len(key) >= MIN_PARTIAL_TITLE_KEY and chapter.key.startswith(key)):
                state.next_chapter = index + 1
                state.pending_chapter = None if complete else (chapter.key, key)
                state.heading_stack.clear()
                self._add_section(item, chapter.title, [], state)
                state.chapter = state.heading_stack[-1]
                return True
        return False

    def _add_table(self, item: Any, document: Any, state: DoclingTreeState) -> None:
        text = table_to_text(item)
        if not text:
            return
        state.pending_chapter = None
        ancestors = self._explicit_ancestors(item, document, state)
        target = ancestors[-1] if ancestors else (state.heading_stack or [None])[-1]
        if docling_label(item) == DOCUMENT_INDEX_LABEL:
            self._add_contents(item, text, target, state)
        elif target is not None:
            target.node.text += "\n\n" + text
        else:
            state.preambles.setdefault(page_number(item), []).append(text)

    def _add_contents(
        self, item: Any, text: str, target: SectionEntry | None, state: DoclingTreeState
    ) -> None:
        """A contents list is shown to readers but never searched: it answers no question."""
        if target is not None and target.node.text.strip() == target.title:
            target.node.text += "\n\n" + text
            target.node.node_type = NodeType.CONTENTS.value
            return
        state.contents_count += 1
        page = page_number(item)
        breadcrumbs = [state.title, *([f"Page {page}"] if page else []), "Contents"]
        path = f"{page_label(page)}.contents{state.contents_count}"
        state.nodes.append(
            ParsedNode("Contents", text, breadcrumbs, path, NodeType.CONTENTS.value)
        )

    def _heading_ancestors(
        self, item: Any, explicit: list[SectionEntry], state: DoclingTreeState
    ) -> list[SectionEntry]:
        if state.chapter is not None:
            state.heading_stack[:] = [state.chapter]
            return explicit or [state.chapter]
        level = heading_level(item)
        while state.heading_stack and state.heading_stack[-1].level >= level:
            state.heading_stack.pop()
        return explicit or list(state.heading_stack)

    def _explicit_ancestors(
        self, item: Any, document: Any, state: DoclingTreeState
    ) -> list[SectionEntry]:
        ancestors = []
        parent = getattr(item, "parent", None)
        while parent is not None:
            parent_item = parent.resolve(doc=document)
            section = state.sections.get(item_ref(parent_item))
            if section is not None:
                ancestors.append(section)
            parent = getattr(parent_item, "parent", None)
        return list(reversed(ancestors))

    def _preamble_nodes(self, state: DoclingTreeState) -> list[ParsedNode]:
        nodes = []
        for page, parts in sorted(state.preambles.items(), key=lambda entry: entry[0] or 0):
            breadcrumbs = [state.title, *([f"Page {page}"] if page else [])]
            nodes.append(
                ParsedNode(
                    state.title,
                    "\n\n".join(parts),
                    breadcrumbs,
                    page_label(page),
                    NodeType.PREAMBLE.value,
                )
            )
        return nodes


def title_key(text: str) -> str:
    """Case, spacing and punctuation-insensitive form used to match headings to contents."""
    return "".join(char for char in text.casefold() if char.isalnum())


def _chapter_titles(document: Any) -> list[ChapterTitle]:
    entries = [
        entry
        for item, _ in document.iterate_items(with_groups=False)
        if docling_label(item) == DOCUMENT_INDEX_LABEL
        for entry in contents_entries(item)
    ]
    return [ChapterTitle(entry.title, title_key(entry.title)) for entry in entries if title_key(entry.title)]


def _section_node(
    text: str, title: str, page: int | None, ancestors: list[SectionEntry], ordinal: int
) -> ParsedNode:
    breadcrumbs = [title, *([f"Page {page}"] if page else [])]
    breadcrumbs.extend([*(entry.title for entry in ancestors), text])
    heading_path = [
        f"h{entry.ordinal}_{ltree_label(entry.title, 'section')}" for entry in ancestors
    ]
    heading_path.append(f"h{ordinal}_{ltree_label(text, 'section')}")
    path = ".".join([page_label(page), *heading_path])
    return ParsedNode(text, text, breadcrumbs, path, NodeType.SECTION.value)
