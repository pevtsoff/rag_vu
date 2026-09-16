"""Database operations for chunk records."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.db_enums.node_types import NodeTypes
from app.models.db.chunk import Chunk
from app.models.db.node import Node
from app.models.services.chunk_data import ChunkData


async def save_chunks(
    session: AsyncSession,
    chunks: list[ChunkData],
    embeddings: list[list[float]],
    vector_column: str,
    document_id: str | None = None,
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError(f"chunks/embeddings mismatch: {len(chunks)} != {len(embeddings)}")
    node_ids = {chunk.node_id for chunk in chunks}
    if not node_ids:
        return
    await _delete_existing_chunks(session, node_ids, document_id)
    if vector_column not in {"embedding_big", "embedding_small"}:
        raise ValueError(f"Unsupported embedding column: {vector_column}")
    session.add_all(
        Chunk(
            node_id=chunk.node_id,
            position=chunk.position,
            text=chunk.text,
            **{vector_column: embedding},
        )
        for chunk, embedding in zip(chunks, embeddings)
    )
    await session.commit()


async def _delete_existing_chunks(
    session: AsyncSession, node_ids: set[object], document_id: str | None
) -> None:
    if document_id:
        document_node_ids = select(Node.id).where(Node.document_id == document_id)
        statement = delete(Chunk).where(Chunk.node_id.in_(document_node_ids))
    else:
        statement = delete(Chunk).where(Chunk.node_id.in_(node_ids))
    await session.execute(statement)


async def load_nodes(session: AsyncSession, document_id: str | None) -> list[Node]:
    statement = select(Node).where(Node.text.is_not(None)).order_by(Node.path)
    if document_id:
        statement = statement.where(Node.document_id == document_id)
    result = await session.execute(statement)
    all_nodes = list(result.scalars().all())
    nodes = [
        node
        for node in all_nodes
        if node.node_type in (NodeTypes.ARTICLE.value, NodeTypes.ARTICLE_PART.value)
    ]
    if not nodes:
        return [node for node in all_nodes if (node.text or "").strip()]
    paths_with_parts = {
        str(node.path).rsplit(".", maxsplit=1)[0]
        for node in nodes
        if node.node_type == NodeTypes.ARTICLE_PART.value and node.path
    }
    return [
        node
        for node in nodes
        if node.node_type == NodeTypes.ARTICLE_PART.value
        or (node.node_type == NodeTypes.ARTICLE.value and str(node.path) not in paths_with_parts)
    ]
