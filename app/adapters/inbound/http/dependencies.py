from uuid import UUID

from fastapi import Request

from app.adapters.inbound.http.api_services import ApiServices
from app.application.errors import DocumentNotFoundError


def get_services(request: Request) -> ApiServices:
    return request.app.state.services


def document_id_from_path(doc_id: str) -> UUID:
    """An id that is not a UUID cannot name a document, so it is simply not found."""
    try:
        return UUID(doc_id)
    except (TypeError, ValueError) as exc:
        raise DocumentNotFoundError(f"Document {doc_id} not found") from exc
