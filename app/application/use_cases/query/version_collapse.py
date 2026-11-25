"""Sends a passage that is identical in several versions once, labelled with all of them."""

from dataclasses import replace

from app.domain.retrieval.retrieved_match import RetrievedMatch


def collapse_unchanged(matches: list[RetrievedMatch], budget: int) -> list[RetrievedMatch]:
    """Merge equal passages of one cluster, then order by cluster and version (oldest first)."""
    groups: dict[tuple[str, str], list[RetrievedMatch]] = {}
    unversioned: list[RetrievedMatch] = []
    for match in matches:
        if match.version is None:
            unversioned.append(match)
            continue
        key = (match.version.cluster_id, match.version.content_hash)
        groups.setdefault(key, []).append(match)
    merged = [_merge(group) for group in groups.values()]
    merged.sort(key=_reading_order)
    return (merged + unversioned)[:budget]


def version_count(matches: list[RetrievedMatch]) -> int:
    """The most distinct versions of one cluster present in ``matches``."""
    per_cluster: dict[str, set[int]] = {}
    for match in matches:
        if match.version is not None:
            per_cluster.setdefault(match.version.cluster_id, set()).update(
                match.version.covered_versions
            )
    return max((len(versions) for versions in per_cluster.values()), default=0)


def _merge(group: list[RetrievedMatch]) -> RetrievedMatch:
    best = group[0]
    assert best.version is not None
    versions = tuple(sorted({v for m in group if m.version for v in m.version.covered_versions}))
    node_ids = tuple(dict.fromkeys(node for match in group for node in match.node_ids))
    first = min(group, key=lambda match: match.version.version if match.version else 0)
    version = replace(first.version or best.version, versions=versions)
    return RetrievedMatch(node_ids, first.text, best.score, version)


def _reading_order(match: RetrievedMatch) -> tuple[str, int]:
    version = match.version
    return (version.cluster_id, min(version.covered_versions)) if version else ("", 0)
