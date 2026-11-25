"""Chunker that uses Docling's structure file when the parser produced one."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from docling_core.types.doc import DoclingDocument

from app.adapters.outbound.chunking.docling_chunk_mapper import heading_map, make_docling_chunks
from app.adapters.outbound.chunking.node_chunk_builder import make_chunks
from app.adapters.outbound.chunking.text_chunker import TextChunker
from app.application.ports.chunker import Chunker
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.node import Node
from app.domain.documents.node_type import NodeType


class DoclingHybridChunker(Chunker):
    """Falls back to plain node chunking (e.g. imported laws) without a structure file."""

    def __init__(
        self,
        chunker_factory: Callable[[], Any],
        fallback: Chunker | None = None,
        document_loader: Callable[[str], Any] = DoclingDocument.load_from_json,
    ) -> None:
        self._chunker_factory = chunker_factory
        self._fallback = fallback or TextChunker()
        self._document_loader = document_loader
        self._chunker: Any = None

    async def chunk(self, nodes: list[Node], structure_path: str | None) -> list[ChunkDraft]:
        if not structure_path or not Path(structure_path).is_file():
            return await self._fallback.chunk(nodes, structure_path)
        return await asyncio.to_thread(self._chunk_structured, nodes, structure_path)

    def _chunk_structured(self, nodes: list[Node], structure_path: str) -> list[ChunkDraft]:
        image_nodes = [node for node in nodes if node.node_type == NodeType.IMAGE.value]
        text_nodes = [node for node in nodes if node.node_type != NodeType.IMAGE.value]
        if not text_nodes:
            return make_chunks(image_nodes)
        document = self._document_loader(structure_path)
        # Image nodes are excluded from the heading map so their own chunk positions
        # can never collide with the document-wide positions of Docling chunks.
        chunks = make_docling_chunks(document, self._hybrid_chunker(), heading_map(text_nodes))
        unsearched = {node.id for node in text_nodes if node.node_type == NodeType.CONTENTS.value}
        chunks = [chunk for chunk in chunks if chunk.node_id not in unsearched]
        return [*chunks, *make_chunks(image_nodes)]

    def _hybrid_chunker(self) -> Any:
        if self._chunker is None:
            self._chunker = self._chunker_factory()
        return self._chunker
