from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalLimits:
    candidate_k: int = 30
    rerank_candidate_k: int = 20
    rrf_k: int = 60
    # latest_only=False (docs/tasks/deduplication.md §4.2)
    multi_version_overfetch: int = 4
    k_per_version: int = 2
    version_relevance_floor: float = 0.6
    max_versions: int = 4

    def candidates(self, latest_only: bool) -> int:
        """Per-source candidate count: several versions need room for each of them."""
        return self.candidate_k if latest_only else self.candidate_k * self.multi_version_overfetch
