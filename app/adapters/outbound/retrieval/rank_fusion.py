"""Reciprocal rank fusion of several ranked candidate lists."""

from app.adapters.outbound.retrieval.ranked_candidate import RankedCandidate

# One entry per source: (source name, [(node key, passage text), ...]) best first.
RankedSource = tuple[str, list[tuple[str, str]]]
FULL_TEXT_SOURCE = "bm25"


def fuse_rankings(sources: list[RankedSource], rrf_k: int) -> dict[str, RankedCandidate]:
    """Sum 1/(k + rank) per node so a node found by several sources ranks higher."""
    fused: dict[str, RankedCandidate] = {}
    for source_name, matches in sources:
        for rank, (key, text) in enumerate(matches, start=1):
            candidate = fused.setdefault(key, RankedCandidate(text, [key.removeprefix("node:")]))
            candidate.score += 1.0 / (rrf_k + rank)
            candidate.sources.add(source_name)
            # BM25 rows carry the whole node text; vector rows only the nearest chunk.
            if source_name == FULL_TEXT_SOURCE:
                candidate.text = text
    return fused


def best_first(candidates: dict[str, RankedCandidate]) -> list[tuple[str, RankedCandidate]]:
    return sorted(candidates.items(), key=lambda pair: pair[1].score, reverse=True)
