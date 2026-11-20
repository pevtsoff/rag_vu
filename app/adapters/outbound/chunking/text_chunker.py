"""Chunker that splits node text without any parser structure file."""

from app.adapters.outbound.chunking.node_chunk_builder import make_chunks, select_chunk_sources
from app.application.ports.chunker import Chunker
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.node import Node


class TextChunker(Chunker):
    async def chunk(self, nodes: list[Node], structure_path: str | None) -> list[ChunkDraft]:
        return make_chunks(select_chunk_sources(nodes))
