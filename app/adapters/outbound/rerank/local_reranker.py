"""Client for the in-stack ``reranker`` service (Qwen3-Reranker-0.6B served
via sentence-transformers' CrossEncoder - see reranker_service/main.py).

The service's HTTP contract deliberately mirrors OpenRouter's /v1/rerank
shape, so this adapter is almost identical to ``OpenRouterReranker`` - no
API key, and no required ``model`` field in the request body, since the
service always serves whichever single model it was started with.
"""

from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.ports.reranker import Reranker
from app.domain.retrieval.retrieved_match import RetrievedMatch


class LocalReranker(Reranker):
    def __init__(self, client_factory: HttpClientFactory, base_url: str, top_k: int) -> None:
        self._client_factory = client_factory
        self._url = f"{base_url.rstrip('/')}/rerank"
        self._top_k = top_k

    async def rerank(
        self, query: str, matches: list[RetrievedMatch], limit: int | None = None
    ) -> list[RetrievedMatch]:
        if not matches:
            return []
        top_k = limit or self._top_k
        body = {
            "query": query,
            "documents": [match.text for match in matches],
            "top_n": min(top_k, len(matches)),
        }
        async with self._client_factory() as client:
            response = await client.post(self._url, json=body)
        response.raise_for_status()
        reranked = _ranked_matches(response.json(), matches)
        if not reranked:
            raise ValueError("Local reranker service returned no usable ranked results.")
        return reranked[:top_k]


def _ranked_matches(payload: object, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
    if not isinstance(payload, dict):
        raise ValueError("Local reranker service returned an invalid response.")
    ranked = []
    for result in payload.get("results", []):
        index = result.get("index") if isinstance(result, dict) else None
        if isinstance(index, int) and 0 <= index < len(matches):
            score = float(result.get("relevance_score") or 0.0)
            ranked.append(RetrievedMatch(matches[index].node_ids, matches[index].text, score))
    return ranked
