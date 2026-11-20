"""One AsyncSession shared by every repository for the lifetime of a transaction."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.outbound.persistence.flush import commit_or_conflict
from app.adapters.outbound.persistence.repositories.sqlalchemy_chunk_repository import (
    SqlAlchemyChunkRepository,
)
from app.adapters.outbound.persistence.repositories.sqlalchemy_document_repository import (
    SqlAlchemyDocumentRepository,
)
from app.adapters.outbound.persistence.repositories.sqlalchemy_inbox_repository import (
    SqlAlchemyInboxRepository,
)
from app.adapters.outbound.persistence.repositories.sqlalchemy_node_repository import (
    SqlAlchemyNodeRepository,
)
from app.adapters.outbound.persistence.repositories.sqlalchemy_outbox_repository import (
    SqlAlchemyOutboxRepository,
)
from app.adapters.outbound.persistence.repositories.sqlalchemy_pipeline_repository import (
    SqlAlchemyPipelineRepository,
)
from app.application.ports.unit_of_work import UnitOfWork


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        session = self._session_factory()
        self._session = session
        self.documents = SqlAlchemyDocumentRepository(session)
        self.pipelines = SqlAlchemyPipelineRepository(session)
        self.nodes = SqlAlchemyNodeRepository(session)
        self.chunks = SqlAlchemyChunkRepository(session)
        self.outbox = SqlAlchemyOutboxRepository(session)
        self.inbox = SqlAlchemyInboxRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def commit(self) -> None:
        await commit_or_conflict(self._require_session())

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Use the unit of work inside 'async with'")
        return self._session
