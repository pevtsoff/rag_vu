from uuid import uuid4

from app.application.use_cases.query.answer_prompt import build_answer_messages
from app.application.use_cases.query.reasoning_filter import (
    context_answer_fallback,
    remove_reasoning_leak,
)
from app.application.use_cases.query.retrieval_query import build_retrieval_query
from app.application.use_cases.query.retrieved_context import build_retrieved_context
from app.application.use_cases.query.source_links import append_source_links
from app.domain.retrieval.retrieved_match import RetrievedMatch


def test_context_includes_document_and_hierarchy() -> None:
    context = build_retrieved_context(
        "Legal text", ["Law", "Article 1"], "Article 1", "Federal law"
    )
    assert (
        context
        == "Документ: Federal law\nBreadcrumbs: Law > Article 1\nТекст фрагмента:\nLegal text"
    )
    assert build_retrieved_context("Only text", None) == "Only text"


def test_source_links_are_deduplicated_and_replace_model_sources() -> None:
    first, second = str(uuid4()), str(uuid4())
    matches = [
        RetrievedMatch((first, second), "Breadcrumbs: Закон > Статья 1", 1.0),
        RetrievedMatch((second,), "Breadcrumbs: Another", 0.5),
    ]
    answer = append_source_links("Answer\n\n**Sources:**\n- made up", matches, "http://api.test/")
    assert answer.count("/api/v1/nodes/") == 2
    assert "made up" not in answer
    assert "[Закон \\> Статья 1]" in answer  # Markdown-escaped label
    assert append_source_links("Answer", [], "http://x") == "Answer"


def test_reasoning_filter_and_context_fallback() -> None:
    assert (
        remove_reasoning_leak("Analysis: private\nFinal answer: Rule applies.") == "Rule applies."
    )
    assert remove_reasoning_leak("  Plain answer. ") == "Plain answer."
    assert remove_reasoning_leak("Analysis: no final answer") is None
    match = RetrievedMatch(
        (str(uuid4()),),
        "Breadcrumbs: Закон > Статья 1\nТекст фрагмента:\n1. Первое предложение. Второе предложение.",
        1.0,
    )
    assert context_answer_fallback([match]) == "Первое предложение.\n\nИсточник: Закон > Статья 1"


def test_followup_query_uses_previous_question() -> None:
    history = [{"role": "user", "content": "Какие есть основания?"}]
    assert build_retrieval_query("А статья 10?", history) == "Какие есть основания?\nА статья 10?"
    assert build_retrieval_query("Свежий вопрос", history) == "Свежий вопрос"
    assert build_retrieval_query("А статья 10?", []) == "А статья 10?"


def test_prompt_keeps_recent_history_without_leaked_reasoning() -> None:
    history = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "Analysis: hidden"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]
    messages = build_answer_messages("Q3", history, [], max_history_turns=1)
    assert "(No matching chunks found.)" in messages[0]["content"]
    assert messages[1:] == [
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
        {"role": "user", "content": "Q3"},
    ]
