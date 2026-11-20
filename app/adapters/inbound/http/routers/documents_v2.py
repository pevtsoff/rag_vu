from fastapi import APIRouter, Depends

from app.adapters.inbound.http.api_services import ApiServices
from app.adapters.inbound.http.dependencies import get_services
from app.adapters.inbound.http.routers.document_routes import read_document, search
from app.adapters.inbound.http.schemas.document_response import DocumentResponse
from app.adapters.inbound.http.schemas.search_request import SearchRequest
from app.adapters.inbound.http.schemas.search_response import SearchResponse

router = APIRouter(prefix="/documents", tags=["documents-v2"])


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str, services: ApiServices = Depends(get_services)
) -> DocumentResponse:
    return await read_document(doc_id, services)


@router.post("/search", response_model=list[SearchResponse])
async def search_documents(
    request: SearchRequest, services: ApiServices = Depends(get_services)
) -> list[SearchResponse]:
    return await search(request, services)
