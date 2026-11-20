from dataclasses import dataclass, field

from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.events.domain_event import DomainEvent


@dataclass(frozen=True)
class PersistedStage:
    """What a stage wrote: the events to publish and, if this was the last stage, the run."""

    events: list[DomainEvent] = field(default_factory=list)
    finished_pipeline: Pipeline | None = None
    document: Document | None = None
