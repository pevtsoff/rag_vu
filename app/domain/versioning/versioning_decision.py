from dataclasses import dataclass
from typing import Any

from app.domain.versioning.fingerprint_candidate import FingerprintCandidate
from app.domain.versioning.versioning_outcome import VersioningOutcome
from app.domain.versioning.versioning_source import VersioningSource


@dataclass(frozen=True)
class VersioningDecision:
    outcome: VersioningOutcome
    source: VersioningSource
    match: FingerprintCandidate | None = None
    lexical_similarity: float | None = None

    def as_metadata(self) -> dict[str, Any]:
        """The JSON stored in ``doc_metadata.versioning``."""
        data: dict[str, Any] = {"source": str(self.source), "outcome": str(self.outcome)}
        if self.match is not None:
            data["matched_document_id"] = str(self.match.document_id)
            data["matched_cluster_id"] = str(self.match.cluster_id)
            data["semantic_similarity"] = _rounded(self.match.semantic_similarity)
        if self.lexical_similarity is not None:
            data["lexical_similarity"] = _rounded(self.lexical_similarity)
        return data


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
