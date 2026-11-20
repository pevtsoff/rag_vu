from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalLimits:
    candidate_k: int = 30
    rerank_candidate_k: int = 20
    rrf_k: int = 60
