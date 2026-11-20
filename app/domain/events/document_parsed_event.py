"""A document was converted into structural nodes."""

from dataclasses import dataclass

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class DocumentParsedEvent(PipelineEvent):
    structure_path: str | None
    node_count: int
