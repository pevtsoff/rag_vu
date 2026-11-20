import httpx
import pytest

from app.adapters.outbound.embeddings.embedding_validation import validate_embeddings
from app.adapters.outbound.embeddings.ollama_embedder import OllamaEmbedder
from app.adapters.outbound.embeddings.openrouter_embedder import OpenRouterEmbedder
from app.domain.documents.embedding_task import EmbeddingTask
from tests.unit.adapters.http_mock import body, mock_clients


async def test_ollama_prefixes_queries_and_requests_768_dimensions() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(body(request))
        assert request.url.path == "/api/embed"
        return httpx.Response(200, json={"embeddings": [[0.1] * 768]})

    embedder = OllamaEmbedder(mock_clients(handler), "http://ollama/", "qwen3-embedding:0.6b")
    await embedder.embed(["question"], EmbeddingTask.QUERY)
    await embedder.embed(["passage"], EmbeddingTask.PASSAGE)

    assert seen[0]["input"][0].startswith("Instruct:") and seen[0]["input"][0].endswith("question")
    assert seen[1]["input"] == ["passage"]
    assert seen[0]["dimensions"] == 768 and embedder.dimensions == 768


async def test_openrouter_retries_transient_errors_and_orders_by_index() -> None:
    responses = iter(
        [
            httpx.Response(429),
            httpx.Response(
                200,
                json={"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]},
            ),
        ]
    )
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    embedder = OpenRouterEmbedder(
        mock_clients(lambda request: next(responses)),
        "http://router/v1",
        "key",
        "m:free",
        dimensions=1,
        sleep=sleep,
    )
    vectors = await embedder.embed(["a", "b"], EmbeddingTask.PASSAGE)
    assert vectors == [[1.0], [2.0]] and delays == [1]


async def test_openrouter_requires_an_api_key() -> None:
    embedder = OpenRouterEmbedder(
        mock_clients(lambda r: httpx.Response(200)), "http://r", None, "m"
    )
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        await embedder.embed(["a"], EmbeddingTask.PASSAGE)


def test_validation_rejects_wrong_counts_and_sizes() -> None:
    with pytest.raises(RuntimeError, match="returned 1 vectors for 2 inputs"):
        validate_embeddings([[0.1]], 2, 1)
    with pytest.raises(RuntimeError, match="Expected 3-dimension"):
        validate_embeddings([[0.1]], 1, 3)
