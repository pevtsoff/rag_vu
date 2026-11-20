from uuid import uuid4

import pytest

from app.application.errors import AnswerGenerationError
from app.application.use_cases.query.answer_question import AnswerQuestion
from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.retrieval.retrieved_match import RetrievedMatch
from tests.unit.fakes.fake_ports import (
    FakeChatModel,
    FakeEmbedder,
    FakeRetriever,
    ReversingReranker,
)


def _use_case(
    reply: str, matches: list[RetrievedMatch]
) -> tuple[AnswerQuestion, FakeChatModel, FakeEmbedder]:
    chat, embedder = FakeChatModel(reply), FakeEmbedder(dimensions=2)
    use_case = AnswerQuestion(
        embedder, FakeRetriever(matches), ReversingReranker(), chat, "http://api/", 8
    )
    return use_case, chat, embedder


async def test_answer_uses_reranked_context_cleans_reasoning_and_links_sources() -> None:
    first, second = str(uuid4()), str(uuid4())
    matches = [
        RetrievedMatch((first,), "Breadcrumbs: Закон > Статья 1\nТекст фрагмента:\nA", 0.9),
        RetrievedMatch((second,), "Breadcrumbs: Закон > Статья 2\nТекст фрагмента:\nB", 0.5),
    ]
    use_case, chat, embedder = _use_case("Analysis: hidden\nFinal answer: Grounded.", matches)

    answer = await use_case.execute(
        "А статья 2?", [{"role": "user", "content": "Какие обязанности?"}]
    )

    assert answer.startswith("Grounded.\n\n**Источники:**")
    assert answer.index(second) < answer.index(first)  # reranked order
    assert f"http://api/api/v1/nodes/{first}/html" in answer
    assert embedder.calls == [(["Какие обязанности?\nА статья 2?"], EmbeddingTask.QUERY)]
    system = chat.messages[0][0]["content"]
    assert "Retrieved context" in system and system.index("Статья 2") < system.index("Статья 1")
    assert chat.messages[0][-1] == {"role": "user", "content": "А статья 2?"}


async def test_reasoning_without_final_answer_is_an_error() -> None:
    use_case, _, _ = _use_case("Analysis: only thinking", [])
    with pytest.raises(AnswerGenerationError):
        await use_case.execute("Question", [])
