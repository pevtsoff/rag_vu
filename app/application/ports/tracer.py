"""Creation of trace spans.

A span opened with ``with tracer.span(...)`` becomes the parent of spans opened inside it,
also across ``await``. An exception leaving the block is recorded on the span and re-raised.
"""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

from app.application.ports.trace_span import TraceSpan
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.traced_pipeline_run import TracedPipelineRun


class Tracer(ABC):
    @abstractmethod
    def span(self, name: str, kind: SpanKind = SpanKind.CHAIN) -> AbstractContextManager[TraceSpan]:
        """Open a child of the current span, or a new trace when there is none."""

    @abstractmethod
    def record_pipeline(self, run: TracedPipelineRun) -> None:
        """Send a finished pipeline run as a trace of its own, covering its whole duration.

        It is never a child of the current span, and it shares the run's session with the
        traces of the run's stage jobs.
        """
