from app.application.dto.chat_completion import ChatCompletion
from app.application.ports.chat_model import ChatModel
from app.application.ports.tracer import Tracer
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.trace_attributes import LLM_FINISH_REASON

ASSISTANT_ROLE = "assistant"


class TracedChatModel(ChatModel):
    """Decorator: an LLM span with the full prompt (incl. context), reply and token usage."""

    def __init__(self, inner: ChatModel, tracer: Tracer) -> None:
        self._inner = inner
        self._tracer = tracer

    async def complete(self, messages: list[dict[str, str]]) -> ChatCompletion:
        with self._tracer.span("llm.answer", SpanKind.LLM) as span:
            span.set_input(messages)
            span.set_input_messages(messages)
            completion = await self._inner.complete(messages)
            span.set_model(completion.model)
            span.set_output(completion.text)
            span.set_output_messages([{"role": ASSISTANT_ROLE, "content": completion.text}])
            span.set_token_usage(completion.usage)
            span.set_attributes({LLM_FINISH_REASON: completion.finish_reason})
            return completion
