"""Render a retrievable source node as a page."""

from uuid import UUID

from app.application.errors import NodeNotFoundError
from app.application.ports.node_renderer import NodeRenderer
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.domain.documents.node_type import NodeType


class RenderNode:
    def __init__(self, uow_factory: UnitOfWorkFactory, renderer: NodeRenderer) -> None:
        self._uow_factory = uow_factory
        self._renderer = renderer

    async def execute(self, node_id: UUID) -> str:
        async with self._uow_factory() as uow:
            found = await uow.nodes.get_with_document_title(node_id)
        if found is None or found[0].node_type not in NodeType.retrievable():
            raise NodeNotFoundError(f"Node {node_id} not found")
        node, document_title = found
        return self._renderer.render(node, document_title)
