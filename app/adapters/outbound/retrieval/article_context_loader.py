"""Loads a full legal article, or its ordered parts when the article node is empty."""

from typing import Any
from uuid import UUID

from sqlalchemy import Select, Text, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.models.document_model import DocumentModel
from app.adapters.outbound.persistence.models.node_model import NodeModel
from app.application.use_cases.query.retrieved_context import build_retrieved_context
from app.domain.documents.node_type import NodeType

CHILD_TYPES = (NodeType.ARTICLE_SECTION.value, NodeType.ARTICLE_PART.value)


class ArticleContextLoader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, document_id: UUID, article_path: str) -> tuple[str, list[str]] | None:
        """Return the article passage and the ids of every node it was built from."""
        article = (await self._session.execute(self._article(document_id, article_path))).first()
        children = (await self._session.execute(self._children(document_id, article_path))).all()
        if article and article[3]:
            return _context([article, *children], article)
        if not children:
            return None
        return _context(children, children[0])

    def _article(self, document_id: UUID, article_path: str) -> Select:
        return (
            _rows(document_id)
            .where(
                NodeModel.node_type == NodeType.ARTICLE.value,
                cast(NodeModel.path, Text) == article_path,
            )
            .limit(1)
        )

    def _children(self, document_id: UUID, article_path: str) -> Select:
        return (
            _rows(document_id)
            .where(
                NodeModel.node_type.in_(CHILD_TYPES),
                cast(NodeModel.path, Text).like(f"{article_path}.%"),
            )
            .order_by(NodeModel.path)
        )


def _rows(document_id: UUID) -> Select:
    return (
        select(
            NodeModel.id,
            NodeModel.title,
            NodeModel.breadcrumbs,
            NodeModel.text,
            DocumentModel.file_name,
        )
        .join(DocumentModel, DocumentModel.id == NodeModel.document_id)
        .where(NodeModel.document_id == document_id)
    )


def _context(rows: list[Any], header: Any) -> tuple[str, list[str]]:
    text = "\n\n".join(row[3] for row in rows if row[3])
    _, title, breadcrumbs, _, file_name = header
    return build_retrieved_context(text, breadcrumbs, title, file_name), [
        str(row[0]) for row in rows
    ]
