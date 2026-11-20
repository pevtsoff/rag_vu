"""A database transaction spanning every repository."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType

from app.application.ports.chunk_repository import ChunkRepository
from app.application.ports.document_repository import DocumentRepository
from app.application.ports.inbox_repository import InboxRepository
from app.application.ports.node_repository import NodeRepository
from app.application.ports.outbox_repository import OutboxRepository
from app.application.ports.pipeline_repository import PipelineRepository


class UnitOfWork(ABC):
    """Use as ``async with factory() as uow``; leaving without ``commit`` rolls back."""

    documents: DocumentRepository
    pipelines: PipelineRepository
    nodes: NodeRepository
    chunks: ChunkRepository
    outbox: OutboxRepository
    inbox: InboxRepository

    @abstractmethod
    async def __aenter__(self) -> "UnitOfWork": ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    async def commit(self) -> None:
        """Commit; raise ConcurrencyConflictError on a uniqueness conflict."""

    @abstractmethod
    async def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
