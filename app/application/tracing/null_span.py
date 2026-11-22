from collections.abc import Mapping, Sequence

from app.application.dto.token_usage import TokenUsage
from app.application.ports.trace_span import Message, TracePayload, TraceSpan, TraceValue
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.traced_document import TracedDocument


class NullSpan(TraceSpan):
    """Discards everything; used when tracing is disabled."""

    def rename(self, name: str) -> None:
        return None

    def set_attributes(self, attributes: Mapping[str, TraceValue | None]) -> None:
        return None

    def set_input(self, value: TracePayload) -> None:
        return None

    def set_output(self, value: TracePayload) -> None:
        return None

    def set_session(self, session_id: str) -> None:
        return None

    def set_model(self, model_name: str) -> None:
        return None

    def set_top_k(self, top_k: int) -> None:
        return None

    def set_documents(self, role: DocumentRole, documents: Sequence[TracedDocument]) -> None:
        return None

    def set_input_messages(self, messages: Sequence[Message]) -> None:
        return None

    def set_output_messages(self, messages: Sequence[Message]) -> None:
        return None

    def set_token_usage(self, usage: TokenUsage) -> None:
        return None
