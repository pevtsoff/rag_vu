"""Chooses which versions' passages reach the reranker when every version is searched."""

from collections.abc import Callable

from app.adapters.outbound.retrieval.ranked_candidate import RankedCandidate
from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.application.use_cases.query.version_question import NamedVersions
from app.domain.retrieval.match_version import MatchVersion

VersionedCandidate = tuple[RankedCandidate, MatchVersion | None]


def select_versions(
    ranked: list[VersionedCandidate], limits: RetrievalLimits, named: NamedVersions
) -> list[VersionedCandidate]:
    """Per-version cap, relevance floor and version cap, keeping the best-first order.

    The caps are ceilings, not quotas: a version with fewer matching passages sends fewer.
    """
    capped = _per_version_cap(ranked, limits.k_per_version)
    best = _best_score_per_document(capped)
    if not best:
        return capped
    floor = limits.version_relevance_floor * max(best.values())
    relevant = [pair for pair in capped if pair[1] is None or best[pair[1].document_id] >= floor]
    kept = _kept_documents(relevant, best, limits.max_versions, _preference(named))
    return [pair for pair in relevant if pair[1] is None or pair[1].document_id in kept]


def _per_version_cap(ranked: list[VersionedCandidate], k: int) -> list[VersionedCandidate]:
    taken: dict[str, int] = {}
    selected = []
    for candidate, version in ranked:
        if version is not None:
            if taken.get(version.document_id, 0) >= k:
                continue
            taken[version.document_id] = taken.get(version.document_id, 0) + 1
        selected.append((candidate, version))
    return selected


def _best_score_per_document(ranked: list[VersionedCandidate]) -> dict[str, float]:
    best: dict[str, float] = {}
    for candidate, version in ranked:
        if version is not None:
            best[version.document_id] = max(best.get(version.document_id, 0.0), candidate.score)
    return best


def _kept_documents(
    ranked: list[VersionedCandidate],
    best: dict[str, float],
    max_versions: int,
    preference: Callable[[MatchVersion], tuple],
) -> set[str]:
    """At most ``max_versions`` documents per cluster, the preferred ones first."""
    per_cluster: dict[str, dict[str, MatchVersion]] = {}
    for _, version in ranked:
        if version is not None:
            per_cluster.setdefault(version.cluster_id, {})[version.document_id] = version
    kept: set[str] = set()
    for versions in per_cluster.values():
        ordered = sorted(versions.values(), key=lambda v: (*preference(v), -best[v.document_id]))
        kept.update(version.document_id for version in ordered[:max_versions])
    return kept


def _preference(named: NamedVersions) -> Callable[[MatchVersion], tuple]:
    """Versions named in the question first, then the latest one, then by score."""

    def key(version: MatchVersion) -> tuple:
        return (not _is_named(version, named), not version.is_latest)

    return key


def _is_named(version: MatchVersion, named: NamedVersions) -> bool:
    if version.version in named.numbers:
        return True
    years = {version.redaction[-4:]} if version.redaction else set()
    if version.created_at is not None:
        years.add(str(version.created_at.year))
    return bool(years & named.years)
