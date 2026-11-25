"""The document's cluster and version are settled; the pipeline run succeeded."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class DocumentVersionedEvent(PipelineEvent):
    cluster_id: UUID
    version: int
    is_latest: bool
    outcome: str
    source: str
