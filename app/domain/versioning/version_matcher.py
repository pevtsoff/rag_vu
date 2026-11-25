"""Decides whether a new document is a new version, a duplicate or a new document."""

from app.domain.versioning.document_fingerprint import DocumentFingerprint
from app.domain.versioning.fingerprint_candidate import FingerprintCandidate
from app.domain.versioning.min_hasher import lexical_similarity
from app.domain.versioning.versioning_decision import VersioningDecision
from app.domain.versioning.versioning_outcome import VersioningOutcome
from app.domain.versioning.versioning_source import VersioningSource
from app.domain.versioning.versioning_thresholds import VersioningThresholds


class VersionMatcher:
    def __init__(self, thresholds: VersioningThresholds) -> None:
        self._thresholds = thresholds

    def by_identifier(
        self, fingerprint: DocumentFingerprint, match: FingerprintCandidate
    ) -> VersioningDecision:
        """Same legal act: a new version, unless the content is practically identical."""
        lexical = _lexical(fingerprint, match)
        semantic = match.semantic_similarity
        if (
            lexical is not None
            and lexical >= self._thresholds.duplicate_lexical
            and (semantic is None or semantic >= self._thresholds.duplicate_semantic)
        ):
            outcome = VersioningOutcome.DUPLICATE
        else:
            outcome = VersioningOutcome.NEW_VERSION
        return VersioningDecision(outcome, VersioningSource.IDENTIFIER, match, lexical)

    def by_fingerprint(
        self, fingerprint: DocumentFingerprint, candidates: list[FingerprintCandidate]
    ) -> VersioningDecision:
        """Pick the candidate sharing the most wording, then apply the thresholds."""
        scored = [
            (lexical, candidate)
            for candidate in candidates
            if _compatible(fingerprint, candidate)
            and (lexical := _lexical(fingerprint, candidate)) is not None
        ]
        if not scored:
            return VersioningDecision(VersioningOutcome.NEW_DOCUMENT, VersioningSource.NEW)
        lexical, best = max(scored, key=lambda pair: pair[0])
        return VersioningDecision(
            self._outcome(best, lexical), VersioningSource.FINGERPRINT, best, lexical
        )

    def _outcome(self, candidate: FingerprintCandidate, lexical: float) -> VersioningOutcome:
        limits = self._thresholds
        semantic = candidate.semantic_similarity or 0.0
        if semantic >= limits.duplicate_semantic and lexical >= limits.duplicate_lexical:
            return VersioningOutcome.DUPLICATE
        # The lexical floor keeps two different acts on one topic apart: averaged embeddings
        # of such documents easily pass the semantic threshold while sharing little text.
        if semantic >= limits.semantic and limits.lexical_min <= lexical < limits.duplicate_lexical:
            return VersioningOutcome.NEW_VERSION
        return VersioningOutcome.NEW_DOCUMENT


def _compatible(fingerprint: DocumentFingerprint, candidate: FingerprintCandidate) -> bool:
    """Two different legal identifiers are two different acts, whatever the fingerprints say."""
    return not (
        fingerprint.identifier
        and candidate.identifier
        and fingerprint.identifier != candidate.identifier
    )


def _lexical(fingerprint: DocumentFingerprint, candidate: FingerprintCandidate) -> float | None:
    if not candidate.minhash:
        return None
    return lexical_similarity(fingerprint.minhash, candidate.minhash)
