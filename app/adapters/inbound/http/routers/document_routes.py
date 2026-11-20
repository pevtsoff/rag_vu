"""Route handlers shared by API versions."""

from app.adapters.inbound.http.api_services import ApiServices
from app.adapters.inbound.http.dependencies import document_id_from_path
from app.adapters.inbound.http.schemas.document_response import DocumentResponse
from app.adapters.inbound.http.schemas.search_request import SearchRequest
from app.adapters.inbound.http.schemas.search_response import SearchResponse


async def read_document(doc_id: str, services: ApiServices) -> DocumentResponse:
    document = await services.get_document.execute(document_id_from_path(doc_id))
    return DocumentResponse.model_validate(document)


async def search(request: SearchRequest, services: ApiServices) -> list[SearchResponse]:
    matches = await services.search_documents.execute(request.query, request.top_k)
    return [
        SearchResponse(
            id=match.node_ids[0] if match.node_ids else "",
            content=match.text,
            score=match.score,
            node_ids=list(match.node_ids),
        )
        for match in matches
    ]
