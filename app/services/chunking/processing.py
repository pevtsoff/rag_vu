"""End-to-end chunk creation and embedding persistence for a document."""

import asyncio
import os
import re
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.node import Node
from app.services.chunking.builders import make_chunks, make_docling_chunks
from app.services.chunking.docling import create_docling_chunker, load_docling_document
from app.services.chunking.persistence import save_chunks
from app.services.embeddings import (
    create_embeddings,
    embedding_column_name,
    embedding_provider,
)

EMBEDDING_BATCH_SIZE = 32


async def _load_document_nodes(session: AsyncSession, document_id: str) -> list[Node]:
    statement = (
        select(Node)
        .where(Node.document_id == document_id, Node.text.is_not(None))
        .order_by(Node.path)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


def _select_chunk_nodes(document_nodes: list[Node]) -> list[Node]:
    return [node for node in document_nodes if (node.text or "").strip()]


def _heading_map(nodes: list[Node]) -> dict[tuple[str, ...], UUID]:
    heading_to_node = {}
    for node in nodes:
        headings = list(node.breadcrumbs or [])[1:]
        if headings and re.fullmatch(r"Page \d+", headings[0]):
            headings = headings[1:]
        heading_to_node[tuple(headings)] = node.id
    return heading_to_node


async def _create_chunks(nodes: list[Node], docling_json_path: str | None):
    if docling_json_path and os.path.isfile(docling_json_path):
        document = await asyncio.to_thread(load_docling_document, docling_json_path)
        chunker = await asyncio.to_thread(create_docling_chunker)
        docling_chunks = await asyncio.to_thread(
            make_docling_chunks,
            document,
            chunker,
            _heading_map(nodes),
        )
        image_nodes = [node for node in nodes if node.node_type == "image"]
        return [*docling_chunks, *make_chunks(image_nodes)]
    return make_chunks(nodes)


async def _embed_chunks(chunks):
    provider = embedding_provider()
    api_key = os.getenv("OPENROUTER_API_KEY")

    if provider == "openrouter" and not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY to use OpenRouter embeddings.")

    vectors = []
    timeout = httpx.Timeout(connect=10, read=120, write=120, pool=120)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
            vectors.extend(
                await create_embeddings(
                    client=client,
                    texts=[chunk.text for chunk in batch],
                    task="passage",
                    api_key=api_key,
                )
            )
    return vectors


async def process_document_chunks(
    session: AsyncSession, document_id: str, docling_json_path: str | None = None
) -> int:
    document_nodes = await _load_document_nodes(session, document_id)
    nodes = _select_chunk_nodes(document_nodes)

    if not nodes:
        raise ValueError(f"No parsed text nodes found for document {document_id}")

    chunks = await _create_chunks(nodes, docling_json_path)

    if not chunks:
        raise ValueError(f"No text chunks could be created for document {document_id}")

    vectors = await _embed_chunks(chunks)
    await save_chunks(session, chunks, vectors, embedding_column_name(), document_id=document_id)

    return len(chunks)
