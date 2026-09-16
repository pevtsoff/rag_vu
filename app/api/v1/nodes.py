from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_autocommit_session
from app.services.api.nodes_search import get_node_html

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/{node_id}/html", response_class=HTMLResponse)
async def read_node_html(
    node_id: UUID,
    session: AsyncSession = Depends(get_autocommit_session),
) -> HTMLResponse:
    """Return the HTML page for an article or article-part node."""
    page = await get_node_html(session, node_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return HTMLResponse(page)
