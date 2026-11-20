"""SELECT statements for the three retrieval sources."""

from sqlalchemy import Select, Text, cast, func, or_, select

from app.adapters.outbound.persistence.models.chunk_model import ChunkModel
from app.adapters.outbound.persistence.models.document_model import DocumentModel
from app.adapters.outbound.persistence.models.node_model import NodeModel
from app.domain.documents.node_type import NodeType

RETRIEVABLE_TYPES = tuple(sorted(NodeType.retrievable()))
ARTICLE_TYPES = tuple(sorted({*NodeType.article_family(), NodeType.SECTION}))


def vector_candidates(column_name: str, query_vector: list[float], limit: int) -> Select:
    """Nearest chunks; rows: node_id, chunk text, breadcrumbs, title, file name."""
    column = getattr(ChunkModel, column_name)
    return (
        select(
            ChunkModel.node_id,
            ChunkModel.text,
            NodeModel.breadcrumbs,
            NodeModel.title,
            DocumentModel.file_name,
        )
        .join(NodeModel, NodeModel.id == ChunkModel.node_id)
        .join(DocumentModel, DocumentModel.id == NodeModel.document_id)
        .where(column.is_not(None), NodeModel.node_type.in_(RETRIEVABLE_TYPES))
        .order_by(column.cosine_distance(query_vector))
        .limit(limit)
    )


def bm25_candidates(query: str, index_name: str, limit: int) -> Select:
    """Best BM25 nodes (lower distance first); rows: id, title, breadcrumbs, text, file name."""
    # Naming the index explicitly lets the query work as a prepared statement.
    score = NodeModel.text.op("<@>")(func.to_bm25query(query, index_name))
    return (
        _node_rows()
        .where(NodeModel.text.is_not(None), NodeModel.node_type.in_(RETRIEVABLE_TYPES))
        .order_by(score)
        .limit(limit)
    )


def article_candidates(number: str, limit: int) -> Select:
    """Nodes that mention ``Статья <number>``; rows as in ``bm25_candidates``."""
    pattern = f"%Статья {number}%"
    return (
        _node_rows()
        .where(
            NodeModel.node_type.in_(ARTICLE_TYPES),
            or_(
                NodeModel.title.ilike(pattern),
                cast(NodeModel.breadcrumbs, Text).ilike(pattern),
                NodeModel.text.ilike(pattern),
            ),
        )
        .order_by(NodeModel.path)
        .limit(limit)
    )


def _node_rows() -> Select:
    return select(
        NodeModel.id,
        NodeModel.title,
        NodeModel.breadcrumbs,
        NodeModel.text,
        DocumentModel.file_name,
    ).join(DocumentModel, DocumentModel.id == NodeModel.document_id)
