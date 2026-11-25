from uuid import uuid4

import pytest

from app.domain.versioning.document_fingerprint import DocumentFingerprint
from app.domain.versioning.embedding_average import average_embedding
from app.domain.versioning.fingerprint_candidate import FingerprintCandidate
from app.domain.versioning.law_identifier import law_identifier, law_redaction
from app.domain.versioning.min_hasher import SIGNATURE_SIZE, MinHasher, lexical_similarity
from app.domain.versioning.text_normalization import content_hash
from app.domain.versioning.version_matcher import VersionMatcher
from app.domain.versioning.versioning_outcome import VersioningOutcome
from app.domain.versioning.versioning_source import VersioningSource
from app.domain.versioning.versioning_thresholds import VersioningThresholds

HEADER = (
    "Закон РФ от 07.02.1992 N 2300-1\n(ред. от 14.07.2022)\n"
    '"О защите прав потребителей"\n'
    "Список изменяющих документов\n(в ред. Федеральных законов от 09.01.1996 N 2-ФЗ,"
)
BODY = " ".join(f"Статья {n}. Продавец обязан передать потребителю товар {n}." for n in range(60))


def test_law_identifier_and_redaction_come_from_the_title_not_the_amendment_list() -> None:
    assert law_identifier(HEADER) == "07.02.1992 N 2300-1"
    assert law_redaction(HEADER) == "14.07.2022"
    assert law_identifier("(в ред. Федеральных законов от 09.01.1996 N 2-ФЗ)") is None
    assert law_identifier("Федеральный закон от 27.07.2006 N 152-ФЗ") == "27.07.2006 N 152-ФЗ"
    assert law_identifier("Федеральный закон от 27.07.2006 N 152ФЗ") == "27.07.2006 N 152-ФЗ"


def test_minhash_is_stable_and_estimates_shared_wording() -> None:
    hasher = MinHasher()
    signature = hasher.signature(BODY)
    assert len(signature) == SIGNATURE_SIZE
    assert signature == MinHasher().signature(BODY)  # stored signatures must stay comparable
    assert max(signature) < 2**63  # fits documents.minhash_sig BIGINT[]
    edited = hasher.signature(BODY.replace("Статья 30.", "Статья 30. Изменено:"))
    unrelated = hasher.signature("Налоговый кодекс устанавливает систему налогов и сборов. " * 20)
    assert lexical_similarity(signature, signature) == 1.0
    assert 0.8 < lexical_similarity(signature, edited) < 1.0
    assert lexical_similarity(signature, unrelated) < 0.1


def test_content_hash_ignores_case_and_whitespace() -> None:
    assert content_hash("Статья 18.\n  Права") == content_hash("статья 18. права ")
    assert content_hash("Статья 18.") != content_hash("Статья 19.")


def test_average_embedding_is_weighted_and_normalised() -> None:
    vector = average_embedding([[1.0, 0.0], [0.0, 1.0]], [3.0, 1.0])
    assert vector == pytest.approx([0.9486833, 0.3162278])
    with pytest.raises(ValueError):
        average_embedding([[1.0]], [1.0, 2.0])


def _fingerprint(text: str, identifier: str | None = None) -> DocumentFingerprint:
    return DocumentFingerprint([1.0], MinHasher().signature(text), identifier)


def _candidate(text: str, semantic: float, identifier: str | None = None) -> FingerprintCandidate:
    return FingerprintCandidate(
        uuid4(), uuid4(), 1, semantic, MinHasher().signature(text), identifier
    )


MATCHER = VersionMatcher(VersioningThresholds())


def test_a_small_edit_is_a_new_version_and_identical_text_a_duplicate() -> None:
    edited = BODY.replace("Статья 30.", "Статья 30. Изменено:")
    version = MATCHER.by_fingerprint(_fingerprint(edited), [_candidate(BODY, 0.99)])
    duplicate = MATCHER.by_fingerprint(_fingerprint(BODY), [_candidate(BODY, 0.999)])
    assert (version.outcome, version.source) == (
        VersioningOutcome.NEW_VERSION,
        VersioningSource.FINGERPRINT,
    )
    assert duplicate.outcome is VersioningOutcome.DUPLICATE


def test_a_similar_topic_with_little_shared_text_stays_a_new_document() -> None:
    other = "Налоговый кодекс устанавливает систему налогов и сборов. " * 20
    decision = MATCHER.by_fingerprint(_fingerprint(other), [_candidate(BODY, 0.98)])
    assert decision.outcome is VersioningOutcome.NEW_DOCUMENT
    assert decision.lexical_similarity is not None and decision.lexical_similarity < 0.5


def test_different_legal_identifiers_are_never_merged() -> None:
    fingerprint = _fingerprint(BODY, "07.02.1992 N 2300-1")
    decision = MATCHER.by_fingerprint(fingerprint, [_candidate(BODY, 0.999, "27.07.2006 N 152-ФЗ")])
    assert decision.outcome is VersioningOutcome.NEW_DOCUMENT


def test_the_same_identifier_is_a_new_version_even_after_a_heavy_rewrite() -> None:
    rewritten = "Совершенно новая редакция закона о правах потребителей. " * 30
    match = _candidate(BODY, None, "07.02.1992 N 2300-1")
    decision = MATCHER.by_identifier(_fingerprint(rewritten, "07.02.1992 N 2300-1"), match)
    assert (decision.outcome, decision.source) == (
        VersioningOutcome.NEW_VERSION,
        VersioningSource.IDENTIFIER,
    )
    assert decision.as_metadata()["matched_document_id"] == str(match.document_id)
