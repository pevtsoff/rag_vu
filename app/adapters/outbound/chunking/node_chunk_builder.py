"""Chunks built directly from node text, prefixed with the node's breadcrumbs."""

from app.adapters.outbound.chunking.text_splitter import normalize_text, split_long_part
from app.domain.documents.breadcrumbs import join_breadcrumbs
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.node import Node
from app.domain.documents.node_type import NodeType

BREADCRUMB_SEPARATOR = "\n"


def build_chunk_text(node: Node, content: str) -> str:
    breadcrumbs = join_breadcrumbs(node.breadcrumbs, BREADCRUMB_SEPARATOR)
    content = content.strip()
    return f"{breadcrumbs}\n\n{content}" if breadcrumbs else content


def make_chunks(nodes: list[Node]) -> list[ChunkDraft]:
    chunks = []
    for node in nodes:
        source_text = normalize_text(node.text or "")
        if not source_text:
            continue
        for position, piece in enumerate(split_long_part(source_text)):
            chunks.append(ChunkDraft(node.id, position, build_chunk_text(node, piece)))
    return chunks


def select_chunk_sources(nodes: list[Node]) -> list[Node]:
    """Prefer article parts over their article so the same text is not embedded twice.

    Articles without numbered parts are kept whole.
    """
    part_parents = {
        node.path.rsplit(".", maxsplit=1)[0]
        for node in nodes
        if node.node_type == NodeType.ARTICLE_PART.value and node.path and "." in node.path
    }
    return [
        node
        for node in nodes
        if node.has_text
        and not (node.node_type == NodeType.ARTICLE.value and node.path in part_parents)
    ]
