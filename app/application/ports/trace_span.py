"""One timed, attributed unit of work in a trace."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from app.application.dto.token_usage import TokenUsage
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.traced_document import TracedDocument

TraceValue = str | bool | int | float | Sequence[str] | Sequence[int] | Sequence[float]
# Structured payloads are serialized as JSON by the adapter.
TracePayload = str | Mapping[str, object] | Sequence[object]
Message = Mapping[str, str]


class TraceSpan(ABC):
    @abstractmethod
    def rename(self, name: str) -> None:
        """Change the span's name once what it works on is known."""

    @abstractmethod
    def set_attributes(self, attributes: Mapping[str, TraceValue | None]) -> None:
        """Record attributes; None values are skipped."""

    @abstractmethod
    def set_input(self, value: TracePayload) -> None: ...

    @abstractmethod
    def set_output(self, value: TracePayload) -> None: ...

    @abstractmethod
    def set_session(self, session_id: str) -> None:
        """Group this trace with others of the same session (chat or pipeline run)."""

    @abstractmethod
    def set_model(self, model_name: str) -> None: ...

    @abstractmethod
    def set_top_k(self, top_k: int) -> None: ...

    @abstractmethod
    def set_documents(self, role: DocumentRole, documents: Sequence[TracedDocument]) -> None: ...

    @abstractmethod
    def set_input_messages(self, messages: Sequence[Message]) -> None: ...

    @abstractmethod
    def set_output_messages(self, messages: Sequence[Message]) -> None: ...

    @abstractmethod
    def set_token_usage(self, usage: TokenUsage) -> None: ...
