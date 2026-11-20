import httpx
import pytest

from app.adapters.outbound.llm.free_model_policy import free_model_chain, require_free_model
from app.adapters.outbound.llm.ollama_chat_model import OllamaChatModel
from app.adapters.outbound.llm.openrouter_chat_model import OpenRouterChatModel
from tests.unit.adapters.http_mock import body, mock_clients

MESSAGES = [{"role": "user", "content": "Question"}]


async def test_ollama_chat_posts_messages_without_thinking() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = body(request)
        assert request.url.path == "/api/chat"
        assert (payload["model"], payload["think"], payload["messages"]) == (
            "test-chat",
            False,
            MESSAGES,
        )
        return httpx.Response(200, json={"message": {"content": "Grounded answer."}})

    model = OllamaChatModel(mock_clients(handler), "http://ollama.test", "test-chat", 30)
    assert await model.complete(MESSAGES) == "Grounded answer."


async def test_ollama_empty_answer_is_an_error() -> None:
    model = OllamaChatModel(
        mock_clients(lambda r: httpx.Response(200, json={"message": {}})), "http://o", "m", 1
    )
    with pytest.raises(RuntimeError, match="empty answer"):
        await model.complete(MESSAGES)


async def test_openrouter_sends_the_model_chain_and_returns_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert body(request)["models"] == ["chat:free", "openrouter/free"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "Answer"}}]})

    model = OpenRouterChatModel(
        mock_clients(handler), "http://router.test/v1", "key", ["chat:free", "openrouter/free"]
    )
    assert await model.complete(MESSAGES) == "Answer"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(500, json={"error": "down"}), "HTTP 500"),
        (httpx.Response(200, json={"choices": []}), "returned no answer"),
        (
            httpx.Response(200, json={"choices": [{"message": {}, "finish_reason": "length"}]}),
            "budget",
        ),
    ],
)
async def test_openrouter_errors_are_descriptive(response: httpx.Response, message: str) -> None:
    model = OpenRouterChatModel(mock_clients(lambda r: response), "http://r", "key", ["m:free"])
    with pytest.raises(RuntimeError, match=message):
        await model.complete(MESSAGES)


def test_only_free_openrouter_models_are_allowed() -> None:
    assert require_free_model("sample:free", "MODEL") == "sample:free"
    with pytest.raises(RuntimeError, match="paid model IDs are disabled"):
        require_free_model("sample:paid", "MODEL")
    assert free_model_chain("a:free", "a:free, openrouter/free,") == ["a:free", "openrouter/free"]
