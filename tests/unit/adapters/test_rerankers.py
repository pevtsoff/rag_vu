import json
from uuid import uuid4

import httpx

from app.adapters.outbound.rerank.fallback_reranker import FallbackReranker
from app.adapters.outbound.rerank.ollama_reranker import OllamaReranker
from app.adapters.outbound.rerank.openrouter_reranker import OpenRouterReranker
from app.adapters.outbound.rerank.passthrough_reranker import PassthroughReranker
from app.domain.retrieval.retrieved_match import RetrievedMatch
from tests.unit.adapters.http_mock import body, mock_clients


def _matches(count: int = 3) -> list[RetrievedMatch]:
    return [RetrievedMatch((str(uuid4()),), f"Passage {i}", float(i)) for i in range(count)]


async def test_openrouter_rerank_applies_top_k_and_scores() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/rerank" and body(request)["top_n"] == 2
        results = [
            {"index": 2, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.5},
            {"index": 9},
        ]
        return httpx.Response(200, json={"results": results})

    reranker = OpenRouterReranker(
        mock_clients(handler), "http://router/api/v1", "key", "r:free", top_k=2
    )
    reranked = await reranker.rerank("question", _matches())
    assert [(m.text, m.score) for m in reranked] == [("Passage 2", 0.9), ("Passage 0", 0.5)]


async def test_ollama_rerank_orders_candidates_and_keeps_omitted_ones() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert body(request)["model"] == "test-reranker"
        return httpx.Response(
            200, json={"message": {"content": json.dumps({"ranking": [2, 2, 7]})}}
        )

    reranker = OllamaReranker(mock_clients(handler), "http://ollama.test", "test-reranker", top_k=3)
    reranked = await reranker.rerank("query", _matches())
    assert [m.text for m in reranked] == ["Passage 2", "Passage 0", "Passage 1"]


async def test_failing_reranker_falls_back_to_hybrid_order() -> None:
    failing = OpenRouterReranker(
        mock_clients(lambda r: httpx.Response(503)), "http://r", "k", "r:free", 5
    )
    matches = _matches(4)
    assert await FallbackReranker(failing, top_k=2).rerank("q", matches) == matches[:2]
    assert await FallbackReranker(failing, top_k=2).rerank("q", []) == []


async def test_passthrough_reranker_caps_results() -> None:
    matches = _matches(4)
    assert await PassthroughReranker(top_k=3).rerank("q", matches) == matches[:3]
