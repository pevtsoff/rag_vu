"""Shape checks shared by every embedding provider."""

from typing import Any


def validate_embeddings(embeddings: Any, expected_count: int, dimensions: int) -> list[list[float]]:
    if not isinstance(embeddings, list) or len(embeddings) != expected_count:
        count = len(embeddings) if isinstance(embeddings, list) else "invalid"
        raise RuntimeError(
            f"Embedding provider returned {count} vectors for {expected_count} inputs."
        )
    for embedding in embeddings:
        if not isinstance(embedding, list) or len(embedding) != dimensions:
            size = len(embedding) if isinstance(embedding, list) else "invalid"
            raise RuntimeError(f"Expected {dimensions}-dimension embeddings, got {size}.")
    return embeddings
