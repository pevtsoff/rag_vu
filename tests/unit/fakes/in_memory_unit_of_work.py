import copy
from types import TracebackType

from app.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tests.unit.fakes.in_memory_repositories import (
    InMemoryChunkRepository,
    InMemoryDocumentRepository,
    InMemoryInboxRepository,
    InMemoryNodeRepository,
    InMemoryOutboxRepository,
    InMemoryPipelineRepository,
)
from tests.unit.fakes.in_memory_store import InMemoryStore


class InMemoryUnitOfWork(UnitOfWork):
    """Works on a private copy of the store; ``commit`` publishes it, exit discards it."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._working: InMemoryStore | None = None

    async def __aenter__(self) -> "InMemoryUnitOfWork":
        self._working = copy.deepcopy(self._store)
        self.documents = InMemoryDocumentRepository(self._working)
        self.pipelines = InMemoryPipelineRepository(self._working)
        self.nodes = InMemoryNodeRepository(self._working)
        self.chunks = InMemoryChunkRepository(self._working)
        self.outbox = InMemoryOutboxRepository(self._working)
        self.inbox = InMemoryInboxRepository(self._working)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._working = None

    async def commit(self) -> None:
        assert self._working is not None
        commits = self._store.commits + 1
        self._store.__dict__.update(copy.deepcopy(self._working).__dict__)
        self._store.commits = commits

    async def rollback(self) -> None:
        self._working = copy.deepcopy(self._store)


def uow_factory(store: InMemoryStore) -> UnitOfWorkFactory:
    return lambda: InMemoryUnitOfWork(store)
