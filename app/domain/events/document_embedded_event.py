"""Every chunk of a document has a vector; the pipeline run succeeded."""

from dataclasses import dataclass

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class DocumentEmbeddedEvent(PipelineEvent):
    chunk_count: int
    dimensions: int
