from dataclasses import dataclass, field
from uuid import UUID

from app.domain.documents.chunk import Chunk
from app.domain.documents.document import Document
from app.domain.documents.node import Node
from app.domain.documents.pipeline import Pipeline
from app.domain.events.event_envelope import EventEnvelope
from tests.unit.fakes.inbox_record import InboxRecord


@dataclass
class InMemoryStore:
    """Committed state shared by every InMemoryUnitOfWork created from it."""

    documents: dict[UUID, Document] = field(default_factory=dict)
    pipelines: dict[UUID, Pipeline] = field(default_factory=dict)
    nodes: dict[UUID, Node] = field(default_factory=dict)
    chunks: dict[UUID, Chunk] = field(default_factory=dict)
    vectors: dict[UUID, tuple[int, list[float]]] = field(default_factory=dict)
    outbox: dict[UUID, EventEnvelope] = field(default_factory=dict)
    published: set[UUID] = field(default_factory=set)
    inbox: dict[UUID, InboxRecord] = field(default_factory=dict)
    commits: int = 0

    def outbox_types(self) -> list[str]:
        return [envelope.event_type for envelope in self.outbox.values()]
