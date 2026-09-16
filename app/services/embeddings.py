"""Shared embedding provider for chunk indexing and query retrieval."""

import asyncio
import os

import httpx

from app.config import get_settings

OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_EMBEDDING_MODEL = "nvidia/nemotron-3-embed-1b:free"
OPENROUTER_EMBEDDING_DIMENSIONS = 2048
OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
# Qwen3 Embedding supports Matryoshka dimensions; 768 matches the existing
# embedding_small pgvector column and avoids a schema change for the vector size.
OLLAMA_EMBEDDING_DIMENSIONS = 768
OLLAMA_EMBEDDINGS_URL = "/api/embed"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def embedding_provider() -> str:
    settings = get_settings()
    provider = os.getenv("EMBEDDING_PROVIDER", settings.EMBEDDING_PROVIDER).strip().lower()
    if provider not in {"openrouter", "ollama"}:
        raise RuntimeError("EMBEDDING_PROVIDER must be 'openrouter' or 'ollama'.")
    return provider


def embedding_tokenizer_model_name() -> str:
    """Return the Hugging Face tokenizer matching the configured embedder."""
    settings = get_settings()
    provider = embedding_provider()
    if provider == "ollama":
        return os.getenv("OLLAMA_EMBEDDING_TOKENIZER", settings.OLLAMA_EMBEDDING_TOKENIZER).strip()
    return os.getenv(
        "OPENROUTER_EMBEDDING_TOKENIZER", settings.OPENROUTER_EMBEDDING_TOKENIZER
    ).strip()


def embedding_column_name() -> str:
    return "embedding_small" if embedding_provider() == "ollama" else "embedding_big"


async def create_embeddings(
    client: httpx.AsyncClient,
    texts: list[str],
    task: str,
    api_key: str | None = None,
) -> list[list[float]]:
    """Generate matching document or query vectors with the selected provider."""
    provider = embedding_provider()
    if task not in {"query", "passage"}:
        raise ValueError("task must be 'query' or 'passage'.")

    if provider == "ollama":
        settings = get_settings()
        model = os.getenv("OLLAMA_EMBEDDING_MODEL", settings.OLLAMA_EMBEDDING_MODEL).strip()
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        if not model:
            raise RuntimeError("OLLAMA_EMBEDDING_MODEL cannot be empty.")
        inputs = texts
        if task == "query":
            instruction = (
                "Instruct: Retrieve relevant passages from Russian legal documents "
                "to answer the query.\nQuery: "
            )
            inputs = [f"{instruction}{text}" for text in texts]
        response = await client.post(
            f"{base_url}{OLLAMA_EMBEDDINGS_URL}",
            json={
                "model": model,
                "input": inputs,
                "dimensions": OLLAMA_EMBEDDING_DIMENSIONS,
            },
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        expected_dimensions = OLLAMA_EMBEDDING_DIMENSIONS
    else:
        if not api_key:
            raise RuntimeError("Set OPENROUTER_API_KEY to use OpenRouter embeddings.")
        inputs = [f"{task}: {text}" for text in texts]
        model = get_settings().OPENROUTER_EMBEDDING_MODEL.strip()
        payload = {"model": model, "input": inputs}
        for attempt in range(6):
            response = await client.post(
                OPENROUTER_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            if response.status_code in RETRY_STATUS_CODES:
                if attempt == 5:
                    response.raise_for_status()
                delay = 2**attempt
                print(f"OpenRouter returned {response.status_code}; retrying in {delay}s...")
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()["data"]
            data.sort(key=lambda item: item["index"])
            embeddings = [item["embedding"] for item in data]
            expected_dimensions = OPENROUTER_EMBEDDING_DIMENSIONS
            break
        else:
            raise RuntimeError("Failed to generate embeddings")

    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        count = len(embeddings) if isinstance(embeddings, list) else "invalid"
        raise RuntimeError(f"Embedding provider returned {count} vectors for {len(texts)} inputs.")
    for embedding in embeddings:
        if not isinstance(embedding, list) or len(embedding) != expected_dimensions:
            dimensions = len(embedding) if isinstance(embedding, list) else "invalid"
            raise RuntimeError(
                f"Expected {expected_dimensions}-dimension embeddings, got {dimensions}."
            )
    return embeddings
