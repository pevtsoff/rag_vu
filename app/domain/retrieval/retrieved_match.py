"""A retrieved passage and the source nodes it was built from."""

from dataclasses import dataclass

from app.domain.retrieval.match_version import MatchVersion


@dataclass(frozen=True)
class RetrievedMatch:
    node_ids: tuple[str, ...]
    text: str
    score: float
    version: MatchVersion | None = None
