"""Builds the FastAPI application around injected use cases."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.inbound.http.api_services import ApiServices
from app.adapters.inbound.http.error_handlers import register_error_handlers
from app.adapters.inbound.http.routers import documents_v1, documents_v2, health, nodes_v1


def create_app(
    services: ApiServices, on_shutdown: Callable[[], Awaitable[None]] | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if on_shutdown is not None:
            await on_shutdown()

    app = FastAPI(
        title="RAG-VU API",
        description="Retrieval-Augmented Generation API",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(documents_v1.router, prefix="/api/v1")
    app.include_router(nodes_v1.router, prefix="/api/v1")
    app.include_router(documents_v2.router, prefix="/api/v2")
    return app
