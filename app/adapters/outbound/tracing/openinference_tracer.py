from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from time import time_ns

from openinference.semconv.trace import SpanAttributes
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Status, StatusCode

from app.adapters.outbound.tracing.openinference_span import OpenInferenceSpan
from app.application.ports.trace_span import TraceSpan
from app.application.ports.tracer import Tracer
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.trace_attributes import with_pipeline_id
from app.application.tracing.traced_pipeline_run import TracedPipelineRun

STARTED_AT = "rag.started_at"
PIPELINE_RUN_SPAN = "pipeline"


class OpenInferenceTracer(Tracer):
    """Opens OpenTelemetry spans tagged with their OpenInference span kind."""

    def __init__(self, tracer: trace.Tracer) -> None:
        self._tracer = tracer

    @contextmanager
    def span(self, name: str, kind: SpanKind = SpanKind.CHAIN) -> Iterator[TraceSpan]:
        attributes = _base_attributes(kind, time_ns())
        # The OpenTelemetry context manager records an escaping exception as an ERROR status.
        with self._tracer.start_as_current_span(name, attributes=attributes) as otel_span:
            yield OpenInferenceSpan(otel_span, kind)
            otel_span.set_status(Status(StatusCode.OK))

    def record_pipeline(self, run: TracedPipelineRun) -> None:
        ended_at = _nanoseconds(run.ended_at) if run.ended_at else time_ns()
        started_at = min(_nanoseconds(run.started_at), ended_at) if run.started_at else ended_at
        # An empty context: the run is a trace of its own even when the last stage reports it.
        otel_span = self._tracer.start_span(
            with_pipeline_id(PIPELINE_RUN_SPAN, run.pipeline_id),
            context=Context(),
            start_time=started_at,
            attributes=_base_attributes(SpanKind.CHAIN, started_at),
        )
        _describe_run(OpenInferenceSpan(otel_span, SpanKind.CHAIN), run)
        otel_span.set_status(_run_status(run))
        otel_span.end(end_time=ended_at)


def _base_attributes(kind: SpanKind, started_at: int) -> dict[str, str]:
    return {
        SpanAttributes.OPENINFERENCE_SPAN_KIND: kind.value,
        # Span timestamps are epoch nanoseconds; a readable start time helps filtering.
        STARTED_AT: datetime.fromtimestamp(started_at / 1e9, UTC).isoformat(),
    }


def _nanoseconds(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1_000


def _describe_run(span: OpenInferenceSpan, run: TracedPipelineRun) -> None:
    span.set_attributes(run.attributes)
    span.set_session(str(run.pipeline_id))
    span.set_input(str(run.pipeline_id))
    span.set_output({"status": run.status, "error": run.error})


def _run_status(run: TracedPipelineRun) -> Status:
    if run.error is not None:
        return Status(StatusCode.ERROR, run.error.splitlines()[0][:500])
    return Status(StatusCode.OK)
