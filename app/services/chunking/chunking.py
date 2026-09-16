"""Public entry point for chunk creation, persistence, and CLI execution."""

import argparse
import asyncio
import os

import httpx
from dotenv import load_dotenv

from app.config import get_settings
from app.models.services.chunk_data import ChunkData
from app.services.chunking import builders as builders_service
from app.services.chunking import docling as docling_service
from app.services.chunking.builders import NodeIdOrHeadingMap, make_chunks
from app.services.chunking.connection import create_database_session_factory
from app.services.chunking.docling import (
    AutoTokenizer,
    DoclingDocument,
    HuggingFaceTokenizer,
    HybridChunker,
)
from app.services.chunking.persistence import load_nodes, save_chunks
from app.services.embeddings import (
    create_embeddings,
    embedding_column_name,
    embedding_provider,
    embedding_tokenizer_model_name,
)

load_dotenv()
EMBEDDING_BATCH_SIZE = 32


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create pgvector chunks for legal articles and article parts."
    )
    parser.add_argument("--document-id", help="Process only one legal document.")
    parser.add_argument("--dry-run", action="store_true", help="Skip database writes.")
    args = parser.parse_args()
    provider = embedding_provider()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if provider == "openrouter" and not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY to use OpenRouter embeddings.")
    engine, session_factory = create_database_session_factory()
    try:
        async with session_factory() as session:
            await _run_cli(session, args.document_id, args.dry_run, api_key)
    finally:
        await engine.dispose()


def create_docling_chunker() -> HybridChunker:
    return docling_service.create_docling_chunker(
        hybrid_chunker=HybridChunker,
        tokenizer_type=HuggingFaceTokenizer,
        auto_tokenizer=AutoTokenizer,
        settings_loader=get_settings,
        model_name_loader=embedding_tokenizer_model_name,
    )


def make_docling_chunks(
    docling_document: DoclingDocument,
    chunker: HybridChunker,
    node_id_or_heading_map: NodeIdOrHeadingMap,
) -> list[ChunkData]:
    return builders_service.make_docling_chunks(docling_document, chunker, node_id_or_heading_map)


async def _run_cli(session, document_id: str | None, dry_run: bool, api_key: str | None) -> None:
    nodes = await load_nodes(session, document_id)
    print(f"Found {len(nodes)} article_part nodes.")
    chunks = make_chunks(nodes)
    print(f"Generated {len(chunks)} chunks.")
    if not chunks:
        print("Nothing to embed.")
        return
    for chunk in chunks:
        print(f"node={chunk.node_id} position={chunk.position} chars={len(chunk.text)}")
    embeddings = await _embed_cli_chunks(chunks, api_key)
    if dry_run:
        print(f"Dry run complete. Generated {len(chunks)} embeddings.")
        return
    await save_chunks(session, chunks, embeddings, embedding_column_name())
    print(f"Successfully stored {len(chunks)} chunks.")


async def _embed_cli_chunks(chunks: list[ChunkData], api_key: str | None) -> list[list[float]]:
    timeout = httpx.Timeout(connect=10, read=120, write=120, pool=120)
    embeddings = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
            print(f"Embedding {start + 1}-{start + len(batch)} of {len(chunks)}...")
            embeddings.extend(
                await create_embeddings(
                    client=client,
                    texts=[chunk.text for chunk in batch],
                    task="passage",
                    api_key=api_key,
                )
            )
    return embeddings


if __name__ == "__main__":
    asyncio.run(main())
