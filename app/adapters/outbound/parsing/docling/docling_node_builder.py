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
from app.adapters.outbound.parsing.docling.docling_tree_state import DoclingTreeState
from app.adapters.outbound.parsing.docling.section_entry import SectionEntry
from app.adapters.outbound.parsing.ltree_label import ltree_label
from app.domain.documents.node_type import NodeType
from app.domain.documents.parsed_node import ParsedNode

SECTION_HEADER_LABEL = "section_header"


class DoclingNodeBuilder:
    """Section headers become section nodes; other text joins the nearest section.

    Text before the first heading of a page becomes that page's preamble node.
    """

    def build(self, document: Any, title: str) -> list[ParsedNode]:
        state = DoclingTreeState(title=title)
        for item, _ in document.iterate_items(with_groups=False):
            self._visit(item, document, state)
        state.nodes[:0] = self._preamble_nodes(state)
        if not state.nodes:
            state.nodes.append(ParsedNode(title, "", [title], "n1", NodeType.HEADER.value))
        return state.nodes

    def _visit(self, item: Any, document: Any, state: DoclingTreeState) -> None:
        text = item_text(item)
        if not text:
            return
        ancestors = self._explicit_ancestors(item, document, state)
        if docling_label(item) == SECTION_HEADER_LABEL:
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

    def _heading_ancestors(
        self, item: Any, explicit: list[SectionEntry], state: DoclingTreeState
    ) -> list[SectionEntry]:
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
