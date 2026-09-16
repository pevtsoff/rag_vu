from uuid import UUID

from jinja2 import Environment, PackageLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.document import Document
from app.models.db.node import Node

_templates = Environment(
    loader=PackageLoader("app.services.api", "templates"),
    autoescape=select_autoescape(("html", "xml")),
)
_RENDERABLE_NODE_TYPES = ("article", "article_part", "section", "preamble", "header")


async def get_node_html(session: AsyncSession, node_id: UUID) -> str | None:
    """Find a renderable legal node and render it with its document metadata."""
    result = await session.execute(
        select(Node, Document.file_name)
        .join(Document, Document.id == Node.document_id)
        .where(
            Node.id == node_id,
            Node.node_type.in_(_RENDERABLE_NODE_TYPES),
        )
    )
    row = result.one_or_none()
    if row is None:
        return None

    node, document_title = row
    if node.node_type not in _RENDERABLE_NODE_TYPES:
        return None
    template = _templates.get_template("node.html")
    return template.render(
        document_title=document_title or "",
        title=node.title or "Legal text",
        breadcrumbs=node.breadcrumbs or [],
        text=node.text or "",
        node_type=node.node_type,
    )
