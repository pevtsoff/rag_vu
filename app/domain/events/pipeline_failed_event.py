"""A pipeline stage failed and the run stopped."""

from dataclasses import dataclass

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class PipelineFailedEvent(PipelineEvent):
    stage: str
    error: str
