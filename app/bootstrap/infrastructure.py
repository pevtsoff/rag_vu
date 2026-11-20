"""Shared infrastructure: database, clock, events, HTTP, embeddings and tracing."""

from functools import cached_property

from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.adapters.outbound.http_client_factory import (
    HttpClientFactory,
    default_http_client_factory,
)
from app.adapters.outbound.persistence.database import create_engine, create_session_factory
from app.adapters.outbound.persistence.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from app.adapters.outbound.system_clock import SystemClock
from app.adapters.outbound.tracing.openinference_tracer import OpenInferenceTracer
from app.adapters.outbound.tracing.phoenix_tracer_provider import create_phoenix_tracer_provider
from app.application.ports.clock import Clock
from app.application.ports.embedder import Embedder
from app.application.ports.tracer import Tracer
from app.application.ports.unit_of_work import UnitOfWork
from app.application.tracing.null_tracer import NullTracer
from app.application.tracing.traced_embedder import TracedEmbedder
from app.application.use_cases.events.default_event_routes import default_event_routes
from app.application.use_cases.events.event_routes import EventRoutes
from app.bootstrap.embedder_wiring import create_embedder
from app.config.app_settings import AppSettings
from app.domain.events.default_event_registry import default_event_registry
from app.domain.events.event_registry import EventRegistry

TRACER_NAME = "rag_vu"


class Infrastructure:
    def __init__(self, settings: AppSettings, null_pool: bool = False) -> None:
        self.settings = settings
        self._null_pool = null_pool

    @cached_property
    def engine(self) -> AsyncEngine:
        return create_engine(
            self.settings.database_url, self._null_pool, self.settings.database_echo
        )

    @cached_property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return create_session_factory(self.engine)

    def unit_of_work(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)

    @cached_property
    def clock(self) -> Clock:
        return SystemClock()

    @cached_property
    def event_registry(self) -> EventRegistry:
        return default_event_registry()

    @cached_property
    def event_routes(self) -> EventRoutes:
        return default_event_routes()

    @cached_property
    def http_client_factory(self) -> HttpClientFactory:
        return default_http_client_factory()

    @cached_property
    def embedder(self) -> Embedder:
        return TracedEmbedder(
            create_embedder(self.settings, self.http_client_factory),
            self.tracer,
            self.settings.embedding_model,
        )

    @cached_property
    def tracer(self) -> Tracer:
        # Built on first use, i.e. inside the Celery child process rather than before fork.
        if not self.settings.tracing_enabled:
            return NullTracer()
        return OpenInferenceTracer(self.tracer_provider.get_tracer(TRACER_NAME))

    @cached_property
    def tracer_provider(self) -> TracerProvider:
        return create_phoenix_tracer_provider(self.settings)

    async def dispose(self) -> None:
        if "engine" in self.__dict__:
            await self.engine.dispose()
        if "tracer_provider" in self.__dict__:
            self.tracer_provider.shutdown()
