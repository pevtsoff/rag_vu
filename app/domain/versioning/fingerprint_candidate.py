"""A latest version of another cluster that the new document may belong to."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class FingerprintCandidate:
    document_id: UUID
    cluster_id: UUID
    version: int
    semantic_similarity: float | None  # None when matched by identifier only
    minhash: tuple[int, ...] | None
    identifier: str | None
