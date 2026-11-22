from contextlib import AbstractContextManager, nullcontext

from app.application.ports.trace_span import TraceSpan
from app.application.ports.tracer import Tracer
from app.application.tracing.null_span import NullSpan
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.traced_pipeline_run import TracedPipelineRun

_NULL_SPAN = NullSpan()


class NullTracer(Tracer):
    """Tracing switched off: every span is a no-op."""

    def span(self, name: str, kind: SpanKind = SpanKind.CHAIN) -> AbstractContextManager[TraceSpan]:
        return nullcontext(_NULL_SPAN)

    def record_pipeline(self, run: TracedPipelineRun) -> None:
        return None
