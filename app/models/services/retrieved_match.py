"""A retrieved passage and its source node identifiers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedMatch:
    node_ids: tuple[str, ...]
    text: str
    score: float
