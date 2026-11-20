"""Maps Docling hybrid-chunker output back to stored nodes via chunk headings."""

import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.node import Node

HeadingNodeMap = Mapping[tuple[str, ...], UUID]
PAGE_CRUMB = re.compile(r"Page \d+")


def heading_map(nodes: list[Node]) -> dict[tuple[str, ...], UUID]:
    """Key each node by its breadcrumbs without the document title and page crumb."""
    mapping = {}
    for node in nodes:
        headings = list(node.breadcrumbs or [])[1:]
        if headings and PAGE_CRUMB.fullmatch(headings[0]):
            headings = headings[1:]
        mapping[tuple(headings)] = node.id
    return mapping


def make_docling_chunks(
    docling_document: Any, chunker: Any, node_ids: HeadingNodeMap | UUID
) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    for position, chunk in enumerate(chunker.chunk(dl_doc=docling_document)):
        text = chunker.contextualize(chunk).strip()
        if text:
            chunks.append(ChunkDraft(resolve_node_id(chunk, node_ids), position, text))
    return chunks


def resolve_node_id(chunk: Any, node_ids: HeadingNodeMap | UUID) -> UUID:
    """Use the deepest heading prefix that names a node, else the document root."""
    if not isinstance(node_ids, Mapping):
        return node_ids
    headings = tuple(getattr(getattr(chunk, "meta", None), "headings", None) or ())
    while headings:
        node_id = node_ids.get(headings)
        if node_id is not None:
            return node_id
        headings = headings[:-1]
    return node_ids.get(()) or next(iter(node_ids.values()))
