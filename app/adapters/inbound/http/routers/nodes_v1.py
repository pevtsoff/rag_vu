from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.adapters.inbound.http.api_services import ApiServices
from app.adapters.inbound.http.dependencies import get_services

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/{node_id}/html", response_class=HTMLResponse)
async def read_node_html(
    node_id: UUID, services: ApiServices = Depends(get_services)
) -> HTMLResponse:
    """Return the page for a retrievable node (article, part, section, preamble, header)."""
    return HTMLResponse(await services.render_node.execute(node_id))
