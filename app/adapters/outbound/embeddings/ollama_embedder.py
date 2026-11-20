"""Embeddings from a local Ollama server."""

from app.adapters.outbound.embeddings.embedding_validation import validate_embeddings
from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.ports.embedder import Embedder
from app.domain.documents.embedding_task import EmbeddingTask

# Qwen3 Embedding supports Matryoshka sizes; 768 fits the ``embedding_small`` column.
OLLAMA_EMBEDDING_DIMENSIONS = 768
QUERY_INSTRUCTION = (
    "Instruct: Retrieve relevant passages from Russian legal documents to answer the query.\n"
    "Query: "
)


class OllamaEmbedder(Embedder):
    def __init__(
        self,
        client_factory: HttpClientFactory,
        base_url: str,
        model: str,
        dimensions: int = OLLAMA_EMBEDDING_DIMENSIONS,
    ) -> None:
        if not model.strip():
            raise ValueError("OLLAMA_EMBEDDING_MODEL cannot be empty.")
        self._client_factory = client_factory
        self._url = f"{base_url.rstrip('/')}/api/embed"
        self._model = model.strip()
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str], task: EmbeddingTask) -> list[list[float]]:
        inputs = (
            [f"{QUERY_INSTRUCTION}{text}" for text in texts]
            if task is EmbeddingTask.QUERY
            else texts
        )
        body = {"model": self._model, "input": inputs, "dimensions": self._dimensions}
        async with self._client_factory() as client:
            response = await client.post(self._url, json=body)
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        return validate_embeddings(embeddings, len(texts), self._dimensions)
