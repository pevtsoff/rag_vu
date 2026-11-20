from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_utils import Ltree

from app.adapters.outbound.persistence.models.chunk_model import ChunkModel
from app.adapters.outbound.persistence.models.document_model import DocumentModel
from app.adapters.outbound.persistence.models.node_model import NodeModel
from app.application.ports.node_repository import NodeRepository
from app.domain.documents.node import Node
from app.domain.documents.parsed_node import ParsedNode


class SqlAlchemyNodeRepository(NodeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_document(self, document_id: UUID, nodes: list[ParsedNode]) -> int:
        # Chunks are removed explicitly so stale vectors cannot outlive a re-parse.
        document_nodes = select(NodeModel.id).where(NodeModel.document_id == document_id)
        await self._session.execute(
            delete(ChunkModel).where(ChunkModel.node_id.in_(document_nodes))
        )
        await self._session.execute(delete(NodeModel).where(NodeModel.document_id == document_id))
        if nodes:
            rows = [_row(document_id, node) for node in nodes]
            await self._session.execute(insert(NodeModel), rows)
        return len(nodes)

    async def list_with_text(self, document_id: UUID) -> list[Node]:
        statement = (
            select(NodeModel)
            .where(NodeModel.document_id == document_id, NodeModel.text.is_not(None))
            .order_by(NodeModel.path)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [node for node in map(_to_entity, rows) if node.has_text]

    async def get_with_document_title(self, node_id: UUID) -> tuple[Node, str] | None:
        statement = (
            select(NodeModel, DocumentModel.file_name)
            .join(DocumentModel, DocumentModel.id == NodeModel.document_id)
            .where(NodeModel.id == node_id)
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        node, file_name = row
        return _to_entity(node), file_name or ""


def _row(document_id: UUID, node: ParsedNode) -> dict:
    return {
        "id": uuid4(),
        "document_id": document_id,
        "title": node.title,
        "text": node.text,
        "node_type": node.node_type,
        "breadcrumbs": node.breadcrumbs,
        "path": Ltree(node.path),
    }


def _to_entity(row: NodeModel) -> Node:
    return Node(
        id=row.id,
        document_id=row.document_id,
        node_type=row.node_type,
        title=row.title,
        text=row.text,
        breadcrumbs=row.breadcrumbs,
        path=str(row.path) if row.path is not None else None,
    )
