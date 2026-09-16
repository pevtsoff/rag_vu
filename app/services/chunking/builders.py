"""Build chunk records from parsed nodes and Docling documents."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.models.db.node import Node
from app.models.services.chunk_data import ChunkData
from app.services.chunking.text import normalize_text, split_long_part

if TYPE_CHECKING:
    from docling.chunking import HybridChunker
    from docling_core.types.doc import DoclingDocument

HeadingNodeMap = Mapping[tuple[str, ...], UUID]
NodeIdOrHeadingMap = HeadingNodeMap | UUID


def format_breadcrumbs(breadcrumbs: object) -> str:

    if not breadcrumbs:
        return ""

    if isinstance(breadcrumbs, str):
        return breadcrumbs.strip()

    if isinstance(breadcrumbs, (list, tuple)):
        return "\n".join(str(item).strip() for item in breadcrumbs if str(item).strip())

    if isinstance(breadcrumbs, dict):
        for key in ("items", "breadcrumbs", "path"):
            value = breadcrumbs.get(key)
            if isinstance(value, (list, tuple)):
                return "\n".join(str(item).strip() for item in value if str(item).strip())

        return "\n".join(str(value).strip() for value in breadcrumbs.values() if str(value).strip())
    return str(breadcrumbs).strip()


def build_chunk_text(node: Node, content: str) -> str:
    breadcrumb_text = format_breadcrumbs(node.breadcrumbs)
    content = content.strip()
    return f"{breadcrumb_text}\n\n{content}" if breadcrumb_text else content


def make_chunks(nodes: list[Node]) -> list[ChunkData]:
    result = []
    for node in nodes:
        source_text = normalize_text(node.text or "")

        if not source_text:
            continue

        for position, piece in enumerate(split_long_part(source_text)):
            result.append(ChunkData(node.id, position, build_chunk_text(node, piece)))

    return result


def make_docling_chunks(
    docling_document: "DoclingDocument",
    chunker: "HybridChunker",
    node_id_or_heading_map: NodeIdOrHeadingMap,
) -> list[ChunkData]:
    result: list[ChunkData] = []

    for position, chunk in enumerate(chunker.chunk(dl_doc=docling_document)):
        text = chunker.contextualize(chunk).strip()

        if text:
            node_id = _resolve_node_id(chunk, node_id_or_heading_map)
            result.append(ChunkData(node_id, position, text))

    return result


def _resolve_node_id(chunk: Any, node_id_or_heading_map: NodeIdOrHeadingMap) -> UUID:
    if not isinstance(node_id_or_heading_map, Mapping):
        return node_id_or_heading_map

    headings = tuple(getattr(getattr(chunk, "meta", None), "headings", None) or ())

    while headings:
        node_id = node_id_or_heading_map.get(headings)
        if node_id is not None:
            return node_id
        headings = headings[:-1]

    return node_id_or_heading_map.get(()) or next(iter(node_id_or_heading_map.values()))
