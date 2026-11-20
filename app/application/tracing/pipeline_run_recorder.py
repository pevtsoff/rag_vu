"""Records the root span of a pipeline run once the run has reached its final status."""

from datetime import datetime

from app.application.ports.trace_span import TraceValue
from app.application.ports.tracer import Tracer
from app.application.tracing.trace_attributes import (
    DOCUMENT_ID,
    PIPELINE_ERROR_STAGE,
    PIPELINE_ID,
    PIPELINE_STAGES_DONE,
    PIPELINE_STATUS,
    document_attributes,
)
from app.application.tracing.traced_pipeline_run import TracedPipelineRun
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage


class PipelineRunRecorder:
    """Call only after the transaction that finished the run has committed.

    Recording earlier could emit a root span for a run whose final status was rolled back,
    and a retry would then emit a second root span with the same id.
    """

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def record(
        self, pipeline: Pipeline, document: Document | None, ended_at: datetime | None = None
    ) -> None:
        if pipeline.is_active:
            raise ValueError(f"Pipeline {pipeline.id} is still {pipeline.status}")
        self._tracer.record_pipeline(
            TracedPipelineRun(
                pipeline_id=pipeline.id,
                status=str(pipeline.status),
                started_at=pipeline.created_at,
                ended_at=ended_at,
                error=pipeline.error_message,
                attributes=_attributes(pipeline, document),
            )
        )


def _attributes(pipeline: Pipeline, document: Document | None) -> dict[str, TraceValue | None]:
    attributes = document_attributes(document) if document is not None else {}
    completed = [str(stage) for stage in PipelineStage if pipeline.is_completed(stage)]
    return {
        **attributes,
        DOCUMENT_ID: str(pipeline.document_id),
        PIPELINE_ID: str(pipeline.id),
        PIPELINE_STATUS: str(pipeline.status),
        PIPELINE_ERROR_STAGE: pipeline.error_stage,
        PIPELINE_STAGES_DONE: completed,
    }
