from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.application.dto.token_usage import TokenUsage
from app.application.ports.trace_span import Message, TracePayload, TraceSpan, TraceValue
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.traced_document import TracedDocument


@dataclass
class RecordingSpan(TraceSpan):
    """Keeps everything a use case records, for assertions."""

    name: str
    kind: SpanKind
    parent: "RecordingSpan | None" = None
    attributes: dict[str, TraceValue] = field(default_factory=dict)
    input: TracePayload | None = None
    output: TracePayload | None = None
    session_id: str | None = None
    model_name: str | None = None
    top_k: int | None = None
    documents: dict[DocumentRole, list[TracedDocument]] = field(default_factory=dict)
    input_messages: list[Message] = field(default_factory=list)
    output_messages: list[Message] = field(default_factory=list)
    usage: TokenUsage | None = None
    error: BaseException | None = None

    def rename(self, name: str) -> None:
        self.name = name

    def set_attributes(self, attributes: Mapping[str, TraceValue | None]) -> None:
        self.attributes.update({k: v for k, v in attributes.items() if v is not None})

    def set_input(self, value: TracePayload) -> None:
        self.input = value

    def set_output(self, value: TracePayload) -> None:
        self.output = value

    def set_session(self, session_id: str) -> None:
        self.session_id = session_id

    def set_model(self, model_name: str) -> None:
        self.model_name = model_name

    def set_top_k(self, top_k: int) -> None:
        self.top_k = top_k

    def set_documents(self, role: DocumentRole, documents: Sequence[TracedDocument]) -> None:
        self.documents[role] = list(documents)

    def set_input_messages(self, messages: Sequence[Message]) -> None:
        self.input_messages = list(messages)

    def set_output_messages(self, messages: Sequence[Message]) -> None:
        self.output_messages = list(messages)

    def set_token_usage(self, usage: TokenUsage) -> None:
        self.usage = usage
