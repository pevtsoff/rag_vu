"""OpenRouter chat completions over a chain of free models."""

from typing import Any

import httpx

from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.ports.chat_model import ChatModel

MAX_ANSWER_TOKENS = 1000
MAX_DETAIL_LENGTH = 1000


class OpenRouterChatModel(ChatModel):
    def __init__(
        self,
        client_factory: HttpClientFactory,
        base_url: str,
        api_key: str | None,
        model_chain: list[str],
    ) -> None:
        self._client_factory = client_factory
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model_chain = model_chain

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self._api_key:
            raise RuntimeError("Set OPENROUTER_API_KEY to use OpenRouter chat.")
        body = {
            "models": self._model_chain,
            "messages": messages,
            "max_tokens": MAX_ANSWER_TOKENS,
            "reasoning": {"enabled": True, "effort": "low", "exclude": True},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with self._client_factory() as client:
            response = await client.post(self._url, headers=headers, json=body)
        return self._answer(_json(response))

    def _answer(self, payload: Any) -> str:
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not choices or not isinstance(choices[0], dict):
            detail = str(payload)[:MAX_DETAIL_LENGTH]
            raise RuntimeError(
                f"OpenRouter model chain {self._model_chain!r} returned no answer: {detail}"
            )
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
        finish_reason = choices[0].get("finish_reason", "unknown")
        if finish_reason == "length":
            raise RuntimeError(
                "OpenRouter exhausted the completion budget before returning answer text "
                "(finish_reason='length'). Try again with less retrieved context or use a "
                "model with a larger completion budget."
            )
        raise RuntimeError(
            f"OpenRouter model chain {self._model_chain!r} returned an empty answer. "
            f"Finish reason: {finish_reason}"
        )


def _json(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError as exc:
        response.raise_for_status()
        raise RuntimeError(
            f"OpenRouter returned a non-JSON response (HTTP {response.status_code})."
        ) from exc
    if not response.is_success:
        error = payload.get("error", payload) if isinstance(payload, dict) else payload
        raise RuntimeError(
            f"OpenRouter chat request failed (HTTP {response.status_code}): "
            f"{str(error)[:MAX_DETAIL_LENGTH]}"
        )
    return payload
