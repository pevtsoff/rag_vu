from collections import Counter
from uuid import NAMESPACE_URL, UUID, uuid5

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
            rows = _rows(document_id, nodes)
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


def _rows(document_id: UUID, nodes: list[ParsedNode]) -> list[dict]:
    # A path can repeat within a document (e.g. the "n1" fallback), so its occurrence number
    # is part of the id too.
    seen: Counter[str] = Counter()
    rows = []
    for node in nodes:
        occurrence = seen[node.path]
        seen[node.path] += 1
        rows.append(_row(document_id, node, occurrence))
    return rows


def stable_node_id(document_id: UUID, path: str, occurrence: int = 0) -> UUID:
    """The same node of the same document keeps its id across re-parses.

    Source links handed out in answers (``/api/v1/nodes/{id}/html``) point at node ids, and
    every re-parse replaces all of a document's nodes; random ids broke every link given out
    before the latest rerun or resumed pipeline.
    """
    return uuid5(NAMESPACE_URL, f"rag_vu:node:{document_id}:{path}:{occurrence}")


def _row(document_id: UUID, node: ParsedNode, occurrence: int) -> dict:
    return {
        "id": stable_node_id(document_id, node.path, occurrence),
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
