"""Maps Docling hybrid-chunker output back to stored nodes via chunk headings."""

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.node import Node

HeadingNodeMap = Mapping[tuple[str, ...], UUID]
PAGE_CRUMB = re.compile(r"Page \d+")
MIN_MERGED_HEADING = 4


def heading_map(nodes: list[Node]) -> dict[tuple[str, ...], UUID]:
    """Key each node by its breadcrumbs without the document title and page crumb.

    A node whose own heading is unique in the document is also keyed by that heading alone:
    Docling names a chunk's headings by its own heading levels, which need not match the
    nesting the node builder chose.
    """
    mapping = {}
    for node in nodes:
        headings = list(node.breadcrumbs or [])[1:]
        if headings and PAGE_CRUMB.fullmatch(headings[0]):
            headings = headings[1:]
        mapping[tuple(headings)] = node.id
    last_headings = Counter(key[-1] for key in mapping if key)
    for key, node_id in list(mapping.items()):
        if len(key) > 1 and last_headings[key[-1]] == 1:
            mapping.setdefault(key[-1:], node_id)
    return mapping


def make_docling_chunks(
    docling_document: Any, chunker: Any, node_ids: HeadingNodeMap | UUID
) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    order = _node_order(node_ids)
    floor = 0
    for position, chunk in enumerate(chunker.chunk(dl_doc=docling_document)):
        text = chunker.contextualize(chunk).strip()
        if text:
            node_id = resolve_node_id(chunk, node_ids, order, floor)
            floor = max(floor, order.get(node_id, 0))
            chunks.append(ChunkDraft(node_id, position, text))
    return chunks


def _node_order(node_ids: HeadingNodeMap | UUID) -> dict[UUID, int]:
    if not isinstance(node_ids, Mapping):
        return {}
    return {node_id: index for index, node_id in enumerate(dict.fromkeys(node_ids.values()))}


def resolve_node_id(
    chunk: Any,
    node_ids: HeadingNodeMap | UUID,
    order: Mapping[UUID, int] | None = None,
    floor: int = 0,
) -> UUID:
    """Use the node of the chunk's nearest heading, else the document root.

    Chunks arrive in document order, so ``floor`` (the furthest node reached so far) settles
    a heading that several nodes could own.
    """
    if not isinstance(node_ids, Mapping):
        return node_ids
    headings = tuple(getattr(getattr(chunk, "meta", None), "headings", None) or ())
    while headings:
        node_id = node_ids.get(headings) or node_ids.get(headings[-1:])
        if node_id is None:
            node_id = _merged_title_node(node_ids, headings[-1], order or {}, floor)
        if node_id is not None:
            return node_id
        headings = headings[:-1]
    return node_ids.get(()) or next(iter(node_ids.values()))


def _merged_title_node(
    node_ids: HeadingNodeMap, heading: str, order: Mapping[UUID, int], floor: int
) -> UUID | None:
    """A chapter title merged from several headings contains each of them."""
    needle = " ".join(heading.casefold().split())
    if len(needle) < MIN_MERGED_HEADING:
        return None
    found = {
        node_id
        for key, node_id in node_ids.items()
        if key and needle in " ".join(key[-1].casefold().split())
    }
    if len(found) == 1:
        return next(iter(found))
    ahead = sorted((node_id for node_id in found if order.get(node_id, 0) >= floor), key=order.get)
    return ahead[0] if ahead else None
