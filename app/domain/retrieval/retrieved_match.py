"""A retrieved passage and the source nodes it was built from."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedMatch:
    node_ids: tuple[str, ...]
    text: str
    score: float
