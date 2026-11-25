from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.ports.reranker import Reranker
from app.domain.retrieval.retrieved_match import RetrievedMatch


class OpenRouterReranker(Reranker):
    def __init__(
        self, client_factory: HttpClientFactory, base_url: str, api_key: str, model: str, top_k: int
    ) -> None:
        self._client_factory = client_factory
        self._url = f"{base_url.rstrip('/')}/rerank"
        self._api_key = api_key
        self._model = model
        self._top_k = top_k

    async def rerank(
        self, query: str, matches: list[RetrievedMatch], limit: int | None = None
    ) -> list[RetrievedMatch]:
        if not matches:
            return []
        top_k = limit or self._top_k
        body = {
            "model": self._model,
            "query": query,
            "documents": [match.text for match in matches],
            "top_n": min(top_k, len(matches)),
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with self._client_factory() as client:
            response = await client.post(self._url, headers=headers, json=body)
        response.raise_for_status()
        reranked = _ranked_matches(response.json(), matches)
        if not reranked:
            raise ValueError("Rerank API returned no usable ranked results.")
        return reranked[:top_k]


def _ranked_matches(payload: object, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
    if not isinstance(payload, dict):
        raise ValueError("Rerank API returned an invalid response.")
    ranked = []
    for result in payload.get("results", []):
        index = result.get("index") if isinstance(result, dict) else None
        if isinstance(index, int) and 0 <= index < len(matches):
            score = float(result.get("relevance_score") or 0.0)
            ranked.append(RetrievedMatch(matches[index].node_ids, matches[index].text, score))
    return ranked
