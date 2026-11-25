"""Every chunk of a document has a vector; the versioning stage runs next."""

from dataclasses import dataclass

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class DocumentEmbeddedEvent(PipelineEvent):
    chunk_count: int
    dimensions: int
