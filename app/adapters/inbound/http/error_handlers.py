"""Translate application errors into HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.errors import (
    ApplicationError,
    ConcurrencyConflictError,
    DocumentNotFoundError,
    NoActivePipelineError,
    NodeNotFoundError,
    StorageError,
)

_RESPONSES: dict[type[ApplicationError], tuple[int, str | None]] = {
    DocumentNotFoundError: (404, "Document not found"),
    NodeNotFoundError: (404, "Node not found"),
    NoActivePipelineError: (409, None),
    ConcurrencyConflictError: (409, None),
    StorageError: (500, None),
}


def register_error_handlers(app: FastAPI) -> None:
    for error_type in _RESPONSES:
        app.add_exception_handler(error_type, _handle)


async def _handle(request: Request, exc: Exception) -> JSONResponse:
    status_code, detail = next(
        (response for error_type, response in _RESPONSES.items() if isinstance(exc, error_type)),
        (500, None),
    )
    return JSONResponse(status_code=status_code, content={"detail": detail or str(exc)})
