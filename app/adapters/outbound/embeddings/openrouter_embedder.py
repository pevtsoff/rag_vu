"""Embeddings from OpenRouter, retried with exponential backoff on transient errors."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.adapters.outbound.embeddings.embedding_validation import validate_embeddings
from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.ports.embedder import Embedder
from app.domain.documents.embedding_task import EmbeddingTask

OPENROUTER_EMBEDDING_DIMENSIONS = 2048
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 6
logger = logging.getLogger(__name__)


class OpenRouterEmbedder(Embedder):
    def __init__(
        self,
        client_factory: HttpClientFactory,
        base_url: str,
        api_key: str | None,
        model: str,
        dimensions: int = OPENROUTER_EMBEDDING_DIMENSIONS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client_factory = client_factory
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._api_key = api_key
        self._model = model.strip()
        self._dimensions = dimensions
        self._sleep = sleep

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str], task: EmbeddingTask) -> list[list[float]]:
        if not self._api_key:
            raise RuntimeError("Set OPENROUTER_API_KEY to use OpenRouter embeddings.")
        body = {"model": self._model, "input": [f"{task.value}: {text}" for text in texts]}
        async with self._client_factory() as client:
            response = await self._post_with_retries(client, body)
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return validate_embeddings(
            [item["embedding"] for item in data], len(texts), self._dimensions
        )

    async def _post_with_retries(self, client: httpx.AsyncClient, body: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        for attempt in range(MAX_ATTEMPTS):
            response = await client.post(self._url, headers=headers, json=body)
            if response.status_code not in RETRY_STATUS_CODES or attempt == MAX_ATTEMPTS - 1:
                response.raise_for_status()
                return response
            delay = 2**attempt
            logger.warning("OpenRouter returned %s; retrying in %ss", response.status_code, delay)
            await self._sleep(delay)
        raise RuntimeError("Failed to generate embeddings")
