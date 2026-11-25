"""The document-level embedding: a weighted, L2-normalised mean of its chunk vectors."""

import math


def average_embedding(vectors: list[list[float]], weights: list[float]) -> list[float]:
    """Weight each chunk by its length so short headers don't dominate the document vector."""
    if not vectors or len(vectors) != len(weights):
        raise ValueError("average_embedding needs one weight per vector")
    size = len(vectors[0])
    total = [0.0] * size
    for vector, weight in zip(vectors, weights, strict=True):
        for index, value in enumerate(vector):
            total[index] += value * weight
    norm = math.sqrt(sum(value * value for value in total))
    if norm == 0:
        raise ValueError("Cannot normalise a zero document vector")
    return [value / norm for value in total]
