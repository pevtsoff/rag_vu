from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.outbound.retrieval.bm25_unavailable_error import Bm25UnavailableError
from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.adapters.outbound.retrieval.sqlalchemy_hybrid_retriever import SqlAlchemyHybridRetriever


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
    session = ScriptedSession([[(True, True)], [], [], rows])
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
        ]
    )
    matches = await _retriever(session).retrieve(VECTOR, "Какие основания?")
    assert matches[0].node_ids == (str(article_id), str(part_id))
    assert "Статья 5. Основания\n\n1. Основание." in matches[0].text


async def test_missing_bm25_index_is_reported() -> None:
    with pytest.raises(Bm25UnavailableError, match="pg_textsearch extension"):
        await _retriever(ScriptedSession([[(False, False)]])).retrieve(VECTOR, "q")
