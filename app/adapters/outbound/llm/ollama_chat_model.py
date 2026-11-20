from typing import Any

from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.dto.chat_completion import ChatCompletion
from app.application.dto.token_usage import TokenUsage
from app.application.ports.chat_model import ChatModel

MAX_ANSWER_TOKENS = 400


class OllamaChatModel(ChatModel):
    def __init__(
        self, client_factory: HttpClientFactory, base_url: str, model: str, timeout: float
    ) -> None:
        if not model.strip():
            raise ValueError("OLLAMA_MODEL cannot be empty.")
        self._client_factory = client_factory
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model.strip()
        self._timeout = timeout

    async def complete(self, messages: list[dict[str, str]]) -> ChatCompletion:
        body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": MAX_ANSWER_TOKENS},
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
            raise RuntimeError("Ollama returned an empty answer.")
        return ChatCompletion(
            text=output,
            model=str(payload.get("model") or self._model),
            usage=_usage(payload),
            finish_reason=payload.get("done_reason"),
        )


def _usage(payload: dict[str, Any]) -> TokenUsage:
    prompt, completion = payload.get("prompt_eval_count"), payload.get("eval_count")
    known = [count for count in (prompt, completion) if isinstance(count, int)]
    return TokenUsage(prompt=prompt, completion=completion, total=sum(known) if known else None)
