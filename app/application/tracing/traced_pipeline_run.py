"""A finished pipeline run, as recorded on the root span of its trace."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.application.ports.trace_span import TraceValue


@dataclass(frozen=True)
class TracedPipelineRun:
    pipeline_id: UUID
    status: str
    started_at: datetime | None
    # None means "now"; callers without a clock (API cancellations) leave it to the tracer.
    ended_at: datetime | None = None
    error: str | None = None
    attributes: Mapping[str, TraceValue | None] = field(default_factory=dict)
