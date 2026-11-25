from datetime import UTC, datetime

from app.adapters.outbound.retrieval.ranked_candidate import RankedCandidate
from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.adapters.outbound.retrieval.version_selection import select_versions
from app.application.use_cases.query.answer_prompt import (
    VERSION_INSTRUCTIONS,
    build_answer_messages,
)
from app.application.use_cases.query.answer_question import AnswerQuestion
from app.application.use_cases.query.version_collapse import collapse_unchanged
from app.application.use_cases.query.version_label import version_label
from app.application.use_cases.query.version_question import (
    NamedVersions,
    asks_about_versions,
    named_versions,
)
from app.domain.retrieval.match_version import MatchVersion
from app.domain.retrieval.retrieved_match import RetrievedMatch
from tests.unit.fakes.fake_ports import (
    FakeChatModel,
    FakeEmbedder,
    FakeRetriever,
    ReversingReranker,
)

CLUSTER = "cluster-1"


def _version(number: int, text_hash: str = "h", latest: bool = False, **fields) -> MatchVersion:
    return MatchVersion(
        document_id=f"doc-v{number}",
        cluster_id=fields.pop("cluster_id", CLUSTER),
        version=number,
        is_latest=latest,
        file_name="law.pdf",
        created_at=fields.pop("created_at", datetime(2020 + number, 1, 1, tzinfo=UTC)),
        redaction=fields.pop("redaction", None),
        content_hash=text_hash,
    )


def _candidate(score: float, version: MatchVersion) -> tuple[RankedCandidate, MatchVersion]:
    return RankedCandidate(f"passage v{version.version}", [f"n{score}"], score), version


def test_history_questions_search_every_version() -> None:
    assert asks_about_versions("Что изменилось в статье 18 между редакциями?")
    assert asks_about_versions("Как было в предыдущей версии?")
    assert not asks_about_versions("Какие права у потребителя по статье 18?")
    assert named_versions("в редакции 2019 года, версия 3") == NamedVersions(
        frozenset({"2019"}), frozenset({3})
    )


def test_each_version_sends_at_most_k_passages() -> None:
    v1, v2 = _version(1), _version(2, latest=True)
    ranked = [_candidate(0.9, v2), _candidate(0.8, v2), _candidate(0.7, v2), _candidate(0.6, v1)]
    selected = select_versions(ranked, RetrievalLimits(k_per_version=2), NamedVersions())
    assert [candidate.score for candidate, _ in selected] == [0.9, 0.8, 0.6]


def test_versions_below_the_relevance_floor_are_dropped() -> None:
    strong, weak = _version(2, latest=True), _version(1)
    ranked = [_candidate(1.0, strong), _candidate(0.3, weak)]
    selected = select_versions(
        ranked, RetrievalLimits(version_relevance_floor=0.6), NamedVersions()
    )
    assert [version.version for _, version in selected] == [2]


def test_the_version_cap_keeps_named_and_latest_versions_first() -> None:
    versions = [_version(n, latest=n == 6) for n in range(1, 7)]
    ranked = [_candidate(1.0 - n / 100, version) for n, version in enumerate(reversed(versions))]
    named = NamedVersions(years=frozenset({"2021"}))  # created_at of v1
    selected = select_versions(ranked, RetrievalLimits(max_versions=2), named)
    assert sorted(version.version for _, version in selected) == [1, 6]


def _match(version: MatchVersion, text: str, score: float = 0.5) -> RetrievedMatch:
    return RetrievedMatch((f"node-{version.version}-{text}",), text, score, version)


def test_unchanged_passages_are_sent_once_with_their_version_range() -> None:
    matches = [
        _match(_version(3, "same"), "Статья 1"),
        _match(_version(1, "same"), "Статья 1"),
        _match(_version(2, "same"), "Статья 1"),
        _match(_version(3, "changed"), "Статья 2 (новая)"),
        _match(_version(1, "old"), "Статья 2"),
    ]
    collapsed = collapse_unchanged(matches, budget=10)
    assert [m.version.covered_versions for m in collapsed] == [(1, 2, 3), (1,), (3,)]
    assert (
        version_label(collapsed[0].version) == "[Doc: law.pdf | v1–v3 (без изменений) | 2021-01-01]"
    )
    assert len(collapsed[0].node_ids) == 3
    assert len(collapse_unchanged(matches, budget=2)) == 2


def test_labels_prefer_the_redaction_date_and_comparison_needs_two_versions() -> None:
    v1, v2 = _version(1, "a", redaction="14.07.2022"), _version(2, "b", latest=True)
    assert version_label(v1) == "[Doc: law.pdf | v1 | ред. от 14.07.2022]"
    single = build_answer_messages("q", [], [_match(v2, "B")], 8)[0]["content"]
    both = build_answer_messages("q", [], [_match(v1, "A"), _match(v2, "B")], 8)[0]["content"]
    assert VERSION_INSTRUCTIONS not in single and "[Doc: law.pdf | v2 | 2022-01-01]\nB" in single
    assert VERSION_INSTRUCTIONS in both


async def test_history_questions_rerank_up_to_the_budget_and_collapse() -> None:
    matches = [_match(_version(n, "same"), "Статья 1", 1 - n / 10) for n in range(1, 4)]
    retriever, chat = FakeRetriever(matches), FakeChatModel("Ответ.")
    use_case = AnswerQuestion(
        FakeEmbedder(2),
        retriever,
        ReversingReranker(),
        chat,
        "http://api",
        8,
        multi_version_budget=10,
    )
    await use_case.execute("Что изменилось в статье 1?", [])
    assert retriever.latest_only == [False]
    assert "v1–v3 (без изменений)" in chat.messages[0][0]["content"]

    await use_case.execute("Что говорит статья 1?", [])
    assert retriever.latest_only == [False, True]
