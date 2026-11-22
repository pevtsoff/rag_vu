"""TraceSpan calls become the OpenInference attributes Phoenix renders."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.adapters.outbound.tracing.openinference_tracer import STARTED_AT, OpenInferenceTracer
from app.application.dto.token_usage import TokenUsage
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.traced_document import TracedDocument
from app.application.tracing.traced_pipeline_run import TracedPipelineRun


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def tracer(exporter: InMemorySpanExporter) -> OpenInferenceTracer:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return OpenInferenceTracer(provider.get_tracer("test"))


def _only(exporter: InMemorySpanExporter) -> ReadableSpan:
    [span] = exporter.get_finished_spans()
    return span


def test_chain_span_has_kind_io_session_and_status(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    with tracer.span("rag.query") as span:
        span.set_input("question")
        span.set_output({"answer": "да"})
        span.set_session("chat-1")
        span.set_attributes({"rag.count": 3, "rag.skipped": None})
    attributes = _only(exporter).attributes

    assert attributes["openinference.span.kind"] == "CHAIN"
    assert (attributes["input.value"], attributes["input.mime_type"]) == ("question", "text/plain")
    assert json.loads(attributes["output.value"]) == {"answer": "да"}
    assert attributes["output.mime_type"] == "application/json"
    assert attributes["session.id"] == "chat-1" and attributes["rag.count"] == 3
    assert "rag.skipped" not in attributes and STARTED_AT in attributes
    assert _only(exporter).status.status_code is StatusCode.OK


def test_reranker_documents_are_flattened(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    documents = [TracedDocument("n1", "text one", 0.8, {"rank": 1})]
    with tracer.span("rerank", SpanKind.RERANKER) as span:
        span.set_input("query")
        span.set_model("rerank-model")
        span.set_top_k(5)
        span.set_documents(DocumentRole.RERANK_INPUT, documents)
        span.set_documents(DocumentRole.RERANK_OUTPUT, documents)
    attributes = _only(exporter).attributes

    assert attributes["reranker.query"] == "query"
    assert attributes["reranker.model_name"] == "rerank-model"
    assert attributes["reranker.top_k"] == 5
    assert attributes["reranker.input_documents.0.document.id"] == "n1"
    assert attributes["reranker.output_documents.0.document.content"] == "text one"
    assert attributes["reranker.output_documents.0.document.score"] == 0.8
    assert json.loads(attributes["reranker.input_documents.0.document.metadata"]) == {"rank": 1}


def test_llm_span_records_messages_model_and_tokens(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    with tracer.span("llm.answer", SpanKind.LLM) as span:
        span.set_model("chat-model")
        span.set_input_messages([{"role": "system", "content": "context"}])
        span.set_output_messages([{"role": "assistant", "content": "answer"}])
        span.set_token_usage(TokenUsage(prompt=10, completion=None, total=10))
    attributes = _only(exporter).attributes

    assert attributes["llm.model_name"] == "chat-model"
    assert attributes["llm.input_messages.0.message.role"] == "system"
    assert attributes["llm.output_messages.0.message.content"] == "answer"
    assert attributes["llm.token_count.prompt"] == 10
    assert "llm.token_count.completion" not in attributes


def test_retrieval_documents_and_embedding_model(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    with tracer.span("retrieval.hybrid", SpanKind.RETRIEVER) as span:
        span.set_documents(DocumentRole.RETRIEVED, [TracedDocument("n1", "text")])
        with tracer.span("embedding.query", SpanKind.EMBEDDING) as child:
            child.set_model("embed-model")
    child_span, parent_span = exporter.get_finished_spans()

    assert parent_span.attributes["retrieval.documents.0.document.id"] == "n1"
    assert child_span.attributes["embedding.model_name"] == "embed-model"
    assert child_span.parent.span_id == parent_span.context.span_id


def test_an_escaping_exception_marks_the_span_as_failed(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    with pytest.raises(ValueError), tracer.span("pipeline.parsing"):
        raise ValueError("broken pdf")
    span = _only(exporter)

    assert span.status.status_code is StatusCode.ERROR
    assert span.events[0].name == "exception"


PIPELINE_ID = UUID("6f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5")
START = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


def _run(**overrides: object) -> TracedPipelineRun:
    values: dict = {
        "pipeline_id": PIPELINE_ID,
        "status": "SUCCEEDED",
        "started_at": START,
        "ended_at": START + timedelta(seconds=42),
        "attributes": {"rag.pipeline.id": str(PIPELINE_ID), "rag.file.name": "law.pdf"},
    }
    return TracedPipelineRun(**{**values, **overrides})


def test_a_span_can_be_renamed_once_its_pipeline_is_known(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    with tracer.span("pipeline.parsing") as span:
        span.rename(f"pipeline.parsing [{PIPELINE_ID}]")

    assert _only(exporter).name == f"pipeline.parsing [{PIPELINE_ID}]"


def test_a_finished_run_is_a_trace_of_its_own_named_after_its_pipeline(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    # The last stage reports the run while its own span is still open.
    with tracer.span("pipeline.embedding"):
        tracer.record_pipeline(_run())
    run, stage = exporter.get_finished_spans()

    assert run.name == f"pipeline [{PIPELINE_ID}]"
    assert run.parent is None and run.context.trace_id != stage.context.trace_id


def test_the_run_trace_covers_the_whole_run_and_describes_it(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    tracer.record_pipeline(_run())
    run = _only(exporter)

    assert (run.end_time - run.start_time) == 42 * 10**9
    assert run.attributes["openinference.span.kind"] == "CHAIN"
    assert run.attributes["session.id"] == str(PIPELINE_ID)
    assert run.attributes["rag.pipeline.id"] == str(PIPELINE_ID)
    assert run.attributes["rag.file.name"] == "law.pdf"
    assert json.loads(run.attributes["output.value"]) == {"status": "SUCCEEDED", "error": None}
    assert run.status.status_code is StatusCode.OK


def test_a_failed_run_trace_has_an_error_status(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    tracer.record_pipeline(_run(status="FAILED", error="ValueError: broken pdf\nTraceback ..."))
    run = _only(exporter)

    assert run.status.status_code is StatusCode.ERROR
    assert run.status.description == "ValueError: broken pdf"


def test_a_run_without_a_known_start_is_recorded_at_its_end(
    tracer: OpenInferenceTracer, exporter: InMemorySpanExporter
) -> None:
    tracer.record_pipeline(_run(started_at=None, ended_at=None))
    run = _only(exporter)

    assert run.start_time == run.end_time
