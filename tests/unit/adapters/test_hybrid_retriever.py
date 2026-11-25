from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.outbound.retrieval.bm25_unavailable_error import Bm25UnavailableError
from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.adapters.outbound.retrieval.sqlalchemy_hybrid_retriever import SqlAlchemyHybridRetriever
from app.application.tracing import trace_attributes as attr
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.span_kind import SpanKind
from tests.unit.fakes.recording_tracer import RecordingTracer


class Result:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def all(self) -> list[tuple]:
        return self.rows

    def first(self) -> tuple | None:
        return self.rows[0] if self.rows else None


class ScriptedSession:
    """Returns queued results in order, standing in for an AsyncSession."""

    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.rolled_back = False

    async def execute(self, statement: object, *parameters: object) -> Result:
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return Result(result)

    async def rollback(self) -> None:
        self.rolled_back = True

    async def __aenter__(self) -> "ScriptedSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _retriever(session: ScriptedSession) -> SqlAlchemyHybridRetriever:
    return SqlAlchemyHybridRetriever(lambda: session, RetrievalLimits(30, 20, 60))


VECTOR = [0.1] * 768
# The query that loads each candidate's document version (labels, version grouping).
NO_VERSIONS: list[tuple] = []


async def test_vector_and_bm25_results_are_fused_by_node() -> None:
    node_id = uuid4()
    session = ScriptedSession(
        [
            [(True, True)],
            [
                (node_id, "vector excerpt", ["Law", "Article 1"], "Article 1", "Law"),
                (node_id, "dup", None, None, "Law"),
            ],
            [(node_id, "Article 1", ["Law", "Article 1"], "full article", "Law")],
            NO_VERSIONS,
        ]
    )
    [match] = await _retriever(session).retrieve(VECTOR, "general query")
    assert match.node_ids == (str(node_id),)
    assert "full article" in match.text
    assert match.score == pytest.approx(2 / 61)


async def test_vector_results_survive_a_bm25_failure() -> None:
    session = ScriptedSession(
        [
            [(True, True)],
            [(uuid4(), "vector excerpt", ["Law"], "Title", "Law")],
            SQLAlchemyError("bm25"),
            NO_VERSIONS,
        ]
    )
    matches = await _retriever(session).retrieve(VECTOR, "general query")
    assert len(matches) == 1 and session.rolled_back


async def test_exact_article_matches_are_added_for_article_questions() -> None:
    node_id, other_id = uuid4(), uuid4()
    rows = [
        (
            node_id,
            "Статья 48. Воинская обязанность",
            ["Закон", "Статья 48. Воинская обязанность"],
            "Article body",
            "Law",
        ),
        (other_id, "Статья 480", ["Закон", "Статья 480"], "Wrong article", "Law"),
    ]
    session = ScriptedSession([[(True, True)], [], [], rows, NO_VERSIONS])
    [match] = await _retriever(session).retrieve(VECTOR, "Что предусмотрено в статье 48?")
    assert match.node_ids == (str(node_id),) and "Article body" in match.text


async def test_list_questions_add_the_whole_parent_article() -> None:
    part_id, article_id, document_id = uuid4(), uuid4(), uuid4()
    session = ScriptedSession(
        [
            [(True, True)],
            [],
            [(part_id, "Пункт 1", ["Закон", "Статья 5"], "1. Основание.", "Law")],
            [(part_id, document_id, "s1.a5.p1", "article_part")],
            [(article_id, "Статья 5", ["Закон", "Статья 5"], "Статья 5. Основания", "Law")],
            [(part_id, "Пункт 1", ["Закон", "Статья 5"], "1. Основание.", "Law")],
            NO_VERSIONS,
        ]
    )
    matches = await _retriever(session).retrieve(VECTOR, "Какие основания?")
    assert matches[0].node_ids == (str(article_id), str(part_id))
    assert "Статья 5. Основания\n\n1. Основание." in matches[0].text


async def test_missing_bm25_index_is_reported() -> None:
    with pytest.raises(Bm25UnavailableError, match="pg_textsearch extension"):
        await _retriever(ScriptedSession([[(False, False)]])).retrieve(VECTOR, "q")


async def test_vector_and_bm25_candidates_are_traced_up_to_top_k() -> None:
    vector_ids, bm25_ids = [uuid4() for _ in range(4)], [uuid4() for _ in range(3)]
    session = ScriptedSession(
        [
            [(True, True)],
            [(node, f"vector {i}", ["Law"], "Title", "Law") for i, node in enumerate(vector_ids)],
            [(node, "Title", ["Law"], f"bm25 {i}", "Law") for i, node in enumerate(bm25_ids)],
            NO_VERSIONS,
        ]
    )
    tracer = RecordingTracer()
    retriever = SqlAlchemyHybridRetriever(
        lambda: session, RetrievalLimits(30, 20, 60), tracer, traced_k=2
    )
    await retriever.retrieve(VECTOR, "general query")

    assert [span.name for span in tracer.spans] == [
        "retrieval.vector",
        "retrieval.bm25",
        "retrieval.article",
    ]
    vector, bm25 = tracer.one("retrieval.vector"), tracer.one("retrieval.bm25")
    assert vector.kind is SpanKind.RETRIEVER and vector.input == "general query"
    assert vector.attributes[attr.RETRIEVAL_CANDIDATE_COUNT] == 4
    assert [d.id for d in vector.documents[DocumentRole.RETRIEVED]] == [
        f"node:{node}" for node in vector_ids[:2]
    ]
    assert bm25.attributes[attr.RETRIEVAL_CANDIDATE_COUNT] == 3
    assert [d.metadata["rank"] for d in bm25.documents[DocumentRole.RETRIEVED]] == [1, 2]


async def test_every_version_is_searched_and_labelled_when_latest_only_is_false() -> None:
    cluster, created = uuid4(), datetime(2024, 1, 1, tzinfo=UTC)
    nodes = [uuid4() for _ in range(4)]
    documents = [uuid4(), uuid4()]
    session = ScriptedSession(
        [
            [(True, True)],
            [
                (node, f"Статья 1, вариант {i}", ["Закон"], "Статья 1", "law.pdf")
                for i, node in enumerate(nodes)
            ],
            [],
            [
                (node, documents[i // 3], cluster, i // 3 + 1, i >= 3, "law.pdf", created, None)
                for i, node in enumerate(nodes)
            ],
        ]
    )
    limits = RetrievalLimits(30, 20, 60, k_per_version=2, version_relevance_floor=0.0)
    matches = await SqlAlchemyHybridRetriever(lambda: session, limits).retrieve(
        VECTOR, "Что изменилось?", latest_only=False
    )

    assert [match.version.version for match in matches] == [1, 1, 2]
    assert all(match.version.cluster_id == str(cluster) for match in matches)
    assert matches[0].version.content_hash != matches[1].version.content_hash
