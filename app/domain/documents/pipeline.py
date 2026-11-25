"""One ingestion run of a document through the ordered stages."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.documents.invalid_stage_transition_error import (
    InvalidStageTransitionError,
)
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus

_COMPLETION_FIELDS = {
    PipelineStage.UPLOADING: ("uploaded", "uploaded_at"),
    PipelineStage.PARSING: ("parsed", "parsed_at"),
    PipelineStage.CHUNKING: ("chunked", "chunked_at"),
    PipelineStage.EMBEDDING: ("embedded", "embedded_at"),
    PipelineStage.VERSIONING: ("versioned", "versioned_at"),
}


@dataclass(kw_only=True)
class Pipeline:
    document_id: UUID
    stage: PipelineStage
    status: PipelineStatus = PipelineStatus.IN_PROGRESS
    id: UUID = field(default_factory=uuid4)
    uploaded: bool = False
    parsed: bool = False
    chunked: bool = False
    embedded: bool = False
    versioned: bool = False
    uploaded_at: datetime | None = None
    parsed_at: datetime | None = None
    chunked_at: datetime | None = None
    embedded_at: datetime | None = None
    versioned_at: datetime | None = None
    error_message: str | None = None
    error_stage: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def start(
        cls, document_id: UUID, stage: PipelineStage, previous: "Pipeline | None" = None
    ) -> "Pipeline":
        """Begin a run at ``stage``; earlier stages are treated as already complete."""
        pipeline = cls(document_id=document_id, stage=stage)
        for completed in stage.preceding():
            completed_at = previous.completed_at(completed) if previous else None
            pipeline._mark_completed(completed, completed_at)
        return pipeline

    @property
    def is_active(self) -> bool:
        return self.status is PipelineStatus.IN_PROGRESS

    def completed_at(self, stage: PipelineStage) -> datetime | None:
        return getattr(self, _COMPLETION_FIELDS[stage][1])

    def is_completed(self, stage: PipelineStage) -> bool:
        return bool(getattr(self, _COMPLETION_FIELDS[stage][0]))

    def complete(self, stage: PipelineStage, at: datetime) -> None:
        """Record ``stage`` as done and move to the next stage or finish the run."""
        if not self.is_active or self.stage is not stage:
            raise InvalidStageTransitionError(
                f"Pipeline {self.id} is {self.status} at {self.stage}; cannot complete {stage}"
            )
        self._mark_completed(stage, at)
        next_stage = stage.next()
        if next_stage is None:
            self.status = PipelineStatus.SUCCEEDED
        else:
            self.stage = next_stage

    def cancel(self) -> None:
        if self.is_active:
            self.status = PipelineStatus.CANCELLED

    def fail(self, stage: PipelineStage | str, message: str) -> None:
        self.status = PipelineStatus.FAILED
        self.error_stage = str(stage)
        self.error_message = message

    def _mark_completed(self, stage: PipelineStage, at: datetime | None) -> None:
        flag, timestamp = _COMPLETION_FIELDS[stage]
        setattr(self, flag, True)
        setattr(self, timestamp, at)
