"""A TraceSpan written as OpenInference attributes, which Phoenix renders natively."""

import json
from collections.abc import Mapping, Sequence

from openinference.semconv.trace import (
    DocumentAttributes,
    MessageAttributes,
    OpenInferenceMimeTypeValues,
    RerankerAttributes,
    SpanAttributes,
)
from opentelemetry.trace import Span

from app.application.dto.token_usage import TokenUsage
from app.application.ports.trace_span import Message, TracePayload, TraceSpan, TraceValue
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.traced_document import TracedDocument

DOCUMENT_PREFIXES = {
    DocumentRole.RETRIEVED: SpanAttributes.RETRIEVAL_DOCUMENTS,
    DocumentRole.RERANK_INPUT: RerankerAttributes.RERANKER_INPUT_DOCUMENTS,
    DocumentRole.RERANK_OUTPUT: RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS,
}
MODEL_NAME_KEYS = {
    SpanKind.LLM: SpanAttributes.LLM_MODEL_NAME,
    SpanKind.EMBEDDING: SpanAttributes.EMBEDDING_MODEL_NAME,
    SpanKind.RERANKER: RerankerAttributes.RERANKER_MODEL_NAME,
}
FALLBACK_MODEL_NAME_KEY = "rag.model_name"
FALLBACK_TOP_K_KEY = "rag.top_k"


class OpenInferenceSpan(TraceSpan):
    def __init__(self, span: Span, kind: SpanKind) -> None:
        self._span = span
        self._kind = kind

    def rename(self, name: str) -> None:
        self._span.update_name(name)

    def set_attributes(self, attributes: Mapping[str, TraceValue | None]) -> None:
        self._span.set_attributes(
            {key: value for key, value in attributes.items() if value is not None}
        )

    def set_input(self, value: TracePayload) -> None:
        self._set_payload(SpanAttributes.INPUT_VALUE, SpanAttributes.INPUT_MIME_TYPE, value)
        if self._kind is SpanKind.RERANKER and isinstance(value, str):
            self._span.set_attribute(RerankerAttributes.RERANKER_QUERY, value)

    def set_output(self, value: TracePayload) -> None:
        self._set_payload(SpanAttributes.OUTPUT_VALUE, SpanAttributes.OUTPUT_MIME_TYPE, value)

    def set_session(self, session_id: str) -> None:
        self._span.set_attribute(SpanAttributes.SESSION_ID, session_id)

    def set_model(self, model_name: str) -> None:
        key = MODEL_NAME_KEYS.get(self._kind, FALLBACK_MODEL_NAME_KEY)
        self._span.set_attribute(key, model_name)

    def set_top_k(self, top_k: int) -> None:
        key = RerankerAttributes.RERANKER_TOP_K if self._kind is SpanKind.RERANKER else None
        self._span.set_attribute(key or FALLBACK_TOP_K_KEY, top_k)

    def set_documents(self, role: DocumentRole, documents: Sequence[TracedDocument]) -> None:
        prefix = DOCUMENT_PREFIXES[role]
        for index, document in enumerate(documents):
            self.set_attributes(_document_attributes(f"{prefix}.{index}", document))

    def set_input_messages(self, messages: Sequence[Message]) -> None:
        self._set_messages(SpanAttributes.LLM_INPUT_MESSAGES, messages)

    def set_output_messages(self, messages: Sequence[Message]) -> None:
        self._set_messages(SpanAttributes.LLM_OUTPUT_MESSAGES, messages)

    def set_token_usage(self, usage: TokenUsage) -> None:
        self.set_attributes(
            {
                SpanAttributes.LLM_TOKEN_COUNT_PROMPT: usage.prompt,
                SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: usage.completion,
                SpanAttributes.LLM_TOKEN_COUNT_TOTAL: usage.total,
            }
        )

    def _set_messages(self, prefix: str, messages: Sequence[Message]) -> None:
        for index, message in enumerate(messages):
            self.set_attributes(
                {
                    f"{prefix}.{index}.{MessageAttributes.MESSAGE_ROLE}": message.get("role"),
                    f"{prefix}.{index}.{MessageAttributes.MESSAGE_CONTENT}": message.get("content"),
                }
            )

    def _set_payload(self, value_key: str, mime_key: str, value: TracePayload) -> None:
        if isinstance(value, str):
            self._span.set_attribute(value_key, value)
            self._span.set_attribute(mime_key, OpenInferenceMimeTypeValues.TEXT.value)
            return
        self._span.set_attribute(value_key, json.dumps(value, ensure_ascii=False, default=str))
        self._span.set_attribute(mime_key, OpenInferenceMimeTypeValues.JSON.value)


def _document_attributes(prefix: str, document: TracedDocument) -> dict[str, TraceValue | None]:
    metadata = json.dumps(document.metadata, ensure_ascii=False) if document.metadata else None
    return {
        f"{prefix}.{DocumentAttributes.DOCUMENT_ID}": document.id,
        f"{prefix}.{DocumentAttributes.DOCUMENT_CONTENT}": document.content,
        f"{prefix}.{DocumentAttributes.DOCUMENT_SCORE}": document.score,
        f"{prefix}.{DocumentAttributes.DOCUMENT_METADATA}": metadata,
    }
