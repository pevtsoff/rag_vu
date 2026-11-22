"""A question leaves one trace: query, embedding, retrieval, rerank and LLM spans."""

import pytest

from app.application.dto.token_usage import TokenUsage
from app.application.errors import AnswerGenerationError
from app.application.tracing import trace_attributes as attr
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.traced_chat_model import TracedChatModel
from app.application.tracing.traced_embedder import TracedEmbedder
from app.application.tracing.traced_reranker import TracedReranker
from app.application.tracing.traced_retriever import TracedRetriever
from app.application.use_cases.query.answer_question import AnswerQuestion
from app.domain.retrieval.retrieved_match import RetrievedMatch
from tests.unit.fakes.fake_ports import (
    FakeChatModel,
    FakeEmbedder,
    FakeRetriever,
    ReversingReranker,
)
from tests.unit.fakes.recording_tracer import RecordingTracer

MATCHES = [
    RetrievedMatch(("a",), "Breadcrumbs: Закон > Статья 1\nТекст фрагмента:\nA", 0.9),
    RetrievedMatch(("b", "c"), "Breadcrumbs: Закон > Статья 2\nТекст фрагмента:\nB", 0.5),
]
CHILD_SPANS = ["embedding.query", "retrieval.hybrid", "rerank", "llm.answer"]


def _use_case(tracer: RecordingTracer, reply: str = "Grounded.") -> AnswerQuestion:
    return AnswerQuestion(
        TracedEmbedder(FakeEmbedder(dimensions=2), tracer, "embed-model"),
        TracedRetriever(FakeRetriever(MATCHES), tracer),
        TracedReranker(ReversingReranker(), tracer, "rerank-model", top_k=5),
        TracedChatModel(FakeChatModel(reply, TokenUsage(900, 40, 940)), tracer),
        "http://api/",
        8,
        tracer,
    )


async def _ask(tracer: RecordingTracer) -> str:
    history = [{"role": "user", "content": "Какие обязанности?"}]
    return await _use_case(tracer).execute("А статья 2?", history, session_id="chat-1")


async def test_query_span_is_the_root_of_every_step() -> None:
    tracer = RecordingTracer()
    answer = await _ask(tracer)
    root = tracer.one("rag.query")

    assert [span.name for span in tracer.spans] == ["rag.query", *CHILD_SPANS]
    assert all(tracer.one(name).parent is root for name in CHILD_SPANS)
    assert (root.input, root.output, root.session_id) == ("А статья 2?", answer, "chat-1")
    assert root.attributes[attr.QUERY_RETRIEVAL_QUERY] == "Какие обязанности?\nА статья 2?"
    assert root.attributes[attr.QUERY_REWRITTEN] is True
    assert root.attributes[attr.QUERY_SOURCE_COUNT] == 2


async def test_retrieval_and_rerank_record_documents_before_and_after() -> None:
    tracer = RecordingTracer()
    await _ask(tracer)
    retrieval, rerank = tracer.one("retrieval.hybrid"), tracer.one("rerank")

    assert retrieval.kind is SpanKind.RETRIEVER
    assert [d.id for d in retrieval.documents[DocumentRole.RETRIEVED]] == ["a", "b,c"]
    assert [d.id for d in rerank.documents[DocumentRole.RERANK_INPUT]] == ["a", "b,c"]
    assert [d.id for d in rerank.documents[DocumentRole.RERANK_OUTPUT]] == ["b,c", "a"]
    assert (rerank.model_name, rerank.top_k) == ("rerank-model", 5)
    assert rerank.attributes[attr.RERANK_ORDER_CHANGED] is True


async def test_llm_span_records_prompt_with_context_reply_and_tokens() -> None:
    tracer = RecordingTracer()
    await _ask(tracer)
    llm = tracer.one("llm.answer")

    assert llm.kind is SpanKind.LLM and llm.model_name == "fake-chat"
    system = llm.input_messages[0]["content"]
    assert "Retrieved context" in system and "Статья 2" in system
    assert llm.input_messages[-1] == {"role": "user", "content": "А статья 2?"}
    assert llm.output_messages == [{"role": "assistant", "content": "Grounded."}]
    assert llm.usage == TokenUsage(900, 40, 940)


async def test_query_embedding_records_the_query_text_and_model() -> None:
    tracer = RecordingTracer()
    await _ask(tracer)
    embedding = tracer.one("embedding.query")

    assert embedding.input == "Какие обязанности?\nА статья 2?"
    assert embedding.model_name == "embed-model"
    assert embedding.attributes[attr.EMBEDDING_DIMENSIONS] == 2


async def test_answer_failure_is_recorded_on_the_query_span() -> None:
    tracer = RecordingTracer()
    with pytest.raises(AnswerGenerationError):
        await _use_case(tracer, reply="Analysis: only thinking").execute("Question", [])
    assert isinstance(tracer.one("rag.query").error, AnswerGenerationError)
    assert tracer.one("rag.query").attributes[attr.QUERY_REASONING_REMOVED] is True
