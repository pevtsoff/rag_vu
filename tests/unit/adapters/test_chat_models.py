import httpx
import pytest

from app.adapters.outbound.llm.free_model_policy import free_model_chain, require_free_model
from app.adapters.outbound.llm.ollama_chat_model import OllamaChatModel
from app.adapters.outbound.llm.openrouter_chat_model import OpenRouterChatModel
from app.application.dto.chat_completion import ChatCompletion
from app.application.dto.token_usage import TokenUsage
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
        return httpx.Response(
            200,
            json={
                "model": "test-chat",
                "message": {"content": "Grounded answer."},
                "done_reason": "stop",
                "prompt_eval_count": 120,
                "eval_count": 30,
            },
        )

    model = OllamaChatModel(mock_clients(handler), "http://ollama.test", "test-chat", 30)
    assert await model.complete(MESSAGES) == ChatCompletion(
        "Grounded answer.", "test-chat", TokenUsage(120, 30, 150), "stop"
    )


async def test_ollama_without_token_counts_reports_unknown_usage() -> None:
    payload = {"message": {"content": "Answer"}}
    model = OllamaChatModel(
        mock_clients(lambda r: httpx.Response(200, json=payload)), "http://o", "m", 1
    )
    completion = await model.complete(MESSAGES)
    assert (completion.model, completion.usage) == ("m", TokenUsage())


async def test_ollama_empty_answer_is_an_error() -> None:
    model = OllamaChatModel(
        mock_clients(lambda r: httpx.Response(200, json={"message": {}})), "http://o", "m", 1
    )
    with pytest.raises(RuntimeError, match="empty answer"):
        await model.complete(MESSAGES)


async def test_ollama_defaults_to_a_2000_token_answer_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert body(request)["options"]["num_predict"] == 2000
        return httpx.Response(200, json={"message": {"content": "Answer"}})

    model = OllamaChatModel(mock_clients(handler), "http://o", "m", 1)
    await model.complete(MESSAGES)


async def test_ollama_uses_a_configured_answer_token_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert body(request)["options"]["num_predict"] == 500
        return httpx.Response(200, json={"message": {"content": "Answer"}})

    model = OllamaChatModel(mock_clients(handler), "http://o", "m", 1, max_answer_tokens=500)
    await model.complete(MESSAGES)


async def test_ollama_reports_budget_exhaustion_distinctly_from_a_true_empty_answer() -> None:
    payload = {"message": {}, "done_reason": "length"}
    model = OllamaChatModel(
        mock_clients(lambda r: httpx.Response(200, json=payload)),
        "http://o",
        "m",
        1,
        max_answer_tokens=400,
    )
    with pytest.raises(RuntimeError, match="exhausted the completion budget"):
        await model.complete(MESSAGES)


async def test_ollama_reports_reasoning_only_content_distinctly() -> None:
    payload = {"message": {"thinking": "I should answer X because..."}, "done_reason": "stop"}
    model = OllamaChatModel(
        mock_clients(lambda r: httpx.Response(200, json=payload)), "http://o", "m", 1
    )
    with pytest.raises(RuntimeError, match="only reasoning/thinking content"):
        await model.complete(MESSAGES)


async def test_openrouter_sends_the_model_chain_and_returns_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert body(request)["models"] == ["chat:free", "openrouter/free"]
        return httpx.Response(
            200,
            json={
                "model": "openrouter/free",
                "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 40, "total_tokens": 940},
            },
        )

    model = OpenRouterChatModel(
        mock_clients(handler), "http://router.test/v1", "key", ["chat:free", "openrouter/free"]
    )
    assert await model.complete(MESSAGES) == ChatCompletion(
        "Answer", "openrouter/free", TokenUsage(900, 40, 940), "stop"
    )


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
