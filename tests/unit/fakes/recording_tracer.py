from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from app.application.ports.trace_span import TraceSpan
from app.application.ports.tracer import Tracer
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.traced_pipeline_run import TracedPipelineRun
from tests.unit.fakes.recording_span import RecordingSpan


class RecordingTracer(Tracer):
    """Records spans in start order, with their parent, like a real tracer would nest them."""

    def __init__(self) -> None:
        self.spans: list[RecordingSpan] = []
        self.runs: list[TracedPipelineRun] = []
        self._open: list[RecordingSpan] = []

    @contextmanager
    def span(self, name: str, kind: SpanKind = SpanKind.CHAIN) -> Iterator[TraceSpan]:
        span = RecordingSpan(name, kind, parent=self._open[-1] if self._open else None)
        self.spans.append(span)
        self._open.append(span)
        try:
            yield span
        except BaseException as exc:
            span.error = exc
            raise
        finally:
            self._open.pop()

    def record_pipeline(self, run: TracedPipelineRun) -> None:
        self.runs.append(run)

    def named(self, name: str) -> list[RecordingSpan]:
        """Spans called ``name``, ignoring the `` [<pipeline id>]`` suffix of pipeline spans."""
        return [span for span in self.spans if span.name.split(" [")[0] == name]

    def one(self, name: str) -> RecordingSpan:
        [span] = self.named(name)
        return span

    def one_run(self, pipeline_id: UUID) -> TracedPipelineRun:
        [run] = [run for run in self.runs if run.pipeline_id == pipeline_id]
        return run
