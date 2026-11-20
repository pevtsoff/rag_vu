"""A document's nodes were split into chunks that still need vectors."""

from dataclasses import dataclass

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class DocumentChunkedEvent(PipelineEvent):
    chunk_count: int
