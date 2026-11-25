from uuid import UUID, uuid4

from sqlalchemy import Select, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.models.chunk_model import ChunkModel
from app.adapters.outbound.persistence.models.node_model import NodeModel
from app.adapters.outbound.persistence.vector_columns import VECTOR_COLUMNS, vector_column_for
from app.application.ports.chunk_repository import ChunkRepository
from app.domain.documents.chunk import Chunk
from app.domain.documents.chunk_draft import ChunkDraft


class SqlAlchemyChunkRepository(ChunkRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_document(self, document_id: UUID, chunks: list[ChunkDraft]) -> int:
        await self._session.execute(
            delete(ChunkModel).where(ChunkModel.node_id.in_(_document_node_ids(document_id)))
        )
        if chunks:
            rows = [
                {
                    "id": uuid4(),
                    "node_id": item.node_id,
                    "position": item.position,
                    "text": item.text,
                }
                for item in chunks
            ]
            await self._session.execute(insert(ChunkModel), rows)
        return len(chunks)

    async def list_for_document(self, document_id: UUID) -> list[Chunk]:
        statement = (
            select(ChunkModel.id, ChunkModel.node_id, ChunkModel.position, ChunkModel.text)
            .join(NodeModel, NodeModel.id == ChunkModel.node_id)
            .where(NodeModel.document_id == document_id)
            .order_by(NodeModel.path, ChunkModel.position)
        )
        rows = (await self._session.execute(statement)).all()
        return [Chunk(id=row[0], node_id=row[1], position=row[2], text=row[3]) for row in rows]

    async def count_for_document(self, document_id: UUID) -> int:
        statement = (
            select(func.count(ChunkModel.id))
            .join(NodeModel, NodeModel.id == ChunkModel.node_id)
            .where(NodeModel.document_id == document_id)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def list_embedded(
        self, document_id: UUID, dimensions: int
    ) -> list[tuple[str, list[float]]]:
        column = getattr(ChunkModel, vector_column_for(dimensions))
        statement = (
            select(ChunkModel.text, column)
            .join(NodeModel, NodeModel.id == ChunkModel.node_id)
            .where(NodeModel.document_id == document_id, column.is_not(None))
            .order_by(NodeModel.path, ChunkModel.position)
        )
        rows = (await self._session.execute(statement)).all()
        return [(row[0], [float(value) for value in row[1]]) for row in rows]

    async def embedded_dimensions(self, document_id: UUID) -> int | None:
        for dimensions, name in VECTOR_COLUMNS.items():
            column = getattr(ChunkModel, name)
            statement = (
                select(ChunkModel.id)
                .join(NodeModel, NodeModel.id == ChunkModel.node_id)
                .where(NodeModel.document_id == document_id, column.is_not(None))
                .limit(1)
            )
            if (await self._session.execute(statement)).first() is not None:
                return dimensions
        return None

    async def store_embeddings(self, vectors: dict[UUID, list[float]], dimensions: int) -> None:
        if not vectors:
            return
        column = vector_column_for(dimensions)
        cleared = {name: None for name in VECTOR_COLUMNS.values() if name != column}
        rows = [{"id": chunk_id, column: vector, **cleared} for chunk_id, vector in vectors.items()]
        await self._session.execute(update(ChunkModel), rows)


def _document_node_ids(document_id: UUID) -> Select:
    return select(NodeModel.id).where(NodeModel.document_id == document_id)
