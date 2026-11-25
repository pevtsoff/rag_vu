from typing import Any

from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.dto.chat_completion import ChatCompletion
from app.application.dto.token_usage import TokenUsage
from app.application.ports.chat_model import ChatModel

DEFAULT_MAX_ANSWER_TOKENS = 2000


class OllamaChatModel(ChatModel):
    def __init__(
        self,
        client_factory: HttpClientFactory,
        base_url: str,
        model: str,
        timeout: float,
        max_answer_tokens: int = DEFAULT_MAX_ANSWER_TOKENS,
    ) -> None:
        if not model.strip():
            raise ValueError("OLLAMA_MODEL cannot be empty.")
        self._client_factory = client_factory
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model.strip()
        self._timeout = timeout
        self._max_answer_tokens = max_answer_tokens

    async def complete(self, messages: list[dict[str, str]]) -> ChatCompletion:
        body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": self._max_answer_tokens},
        }
        async with self._client_factory() as client:
            response = await client.post(self._url, json=body, timeout=self._timeout)
        response.raise_for_status()
        return self._completion(response.json())

    def _completion(self, payload: Any) -> ChatCompletion:
        payload = payload if isinstance(payload, dict) else {}
        message = payload.get("message", {})
        output = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(output, str) or not output.strip():
            raise RuntimeError(self._empty_answer_error(payload, message))
        return ChatCompletion(
            text=output,
            model=str(payload.get("model") or self._model),
            usage=_usage(payload),
            finish_reason=payload.get("done_reason"),
        )

    def _empty_answer_error(self, payload: Any, message: Any) -> str:
        done_reason = payload.get("done_reason", "unknown")
        # A hidden-reasoning model (e.g. gpt-oss) can spend the whole budget on its internal
        # reasoning and never reach the visible answer; Ollama still replies 200 OK with an
        # empty "content" and done_reason="length" -- indistinguishable from a true empty
        # answer unless we check it explicitly.
        if done_reason == "length":
            return (
                f"Ollama ({self._model}) exhausted the completion budget "
                f"({self._max_answer_tokens} tokens) before returning answer text "
                "(done_reason='length'), likely spent on internal reasoning. Try raising "
                "OLLAMA_MAX_ANSWER_TOKENS or using a less 'thinking'-heavy model."
            )
        thinking = message.get("thinking") if isinstance(message, dict) else None
        if isinstance(thinking, str) and thinking.strip():
            return (
                f"Ollama ({self._model}) returned only reasoning/thinking content, no final "
                f"answer (done_reason={done_reason!r})."
            )
        return f"Ollama returned an empty answer. Finish reason: {done_reason!r}"


def _usage(payload: dict[str, Any]) -> TokenUsage:
    prompt, completion = payload.get("prompt_eval_count"), payload.get("eval_count")
    known = [count for count in (prompt, completion) if isinstance(count, int)]
    return TokenUsage(prompt=prompt, completion=completion, total=sum(known) if known else None)
