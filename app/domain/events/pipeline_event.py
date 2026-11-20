"""Base class of events that belong to one pipeline run of a document."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.events.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class PipelineEvent(DomainEvent):
    document_id: UUID
    pipeline_id: UUID

    @property
    def aggregate_id(self) -> UUID | None:
        return self.document_id
