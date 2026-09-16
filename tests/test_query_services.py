"""Unit tests for query context, retrieval, reranking, and answers."""

import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.services.query.answer import (
    build_retrieval_query,
    context_answer_fallback,
    generate_answer,
    generate_answer_with_ollama,
    remove_reasoning_leak,
)
from app.services.query.providers import require_free_model
from app.services.query.rerank import rerank_chunks, rerank_chunks_with_ollama
from app.services.query.retrieve_context import (
    append_source_links,
    build_retrieved_context,
    format_breadcrumbs,
)
from app.services.query.search_chunks import search_chunks
from app.services.query.settings import settings as query_settings
from app.services.query.types import RetrievedMatch


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.rolled_back = False

    async def execute(self, statement, *_parameters):
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return Result(result)

    async def rollback(self):
        self.rolled_back = True


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


class TestQueryHelpers(unittest.TestCase):
    def test_format_breadcrumbs_supports_common_shapes(self):
        self.assertEqual(format_breadcrumbs(["Law", "Article 1"]), "Law > Article 1")
        self.assertEqual(
            format_breadcrumbs({"items": ["Law", "Article 2"]}),
            "Law > Article 2",
        )
        self.assertEqual(format_breadcrumbs(" Law > Article 3 "), "Law > Article 3")

    def test_context_includes_document_and_hierarchy(self):
        context = build_retrieved_context(
            "Legal text", ["Law", "Article 1"], "Article 1", "Federal law"
        )
        self.assertIn("Документ: Federal law", context)
        self.assertIn("Breadcrumbs: Law > Article 1", context)
        self.assertIn("Текст фрагмента:\nLegal text", context)

    def test_source_links_are_deduplicated_and_include_all_source_nodes(self):
        first_id, second_id = str(uuid4()), str(uuid4())
        matches = [
            RetrievedMatch(
                node_ids=(first_id, second_id),
                text="Breadcrumbs: Закон > Статья 1",
                score=1.0,
            ),
            RetrievedMatch(node_ids=(second_id,), text="Breadcrumbs: Another", score=0.5),
        ]
        with patch.object(query_settings, "rag_vu_api_base_url", "http://api.test/"):
            answer = append_source_links("Answer", matches)

        self.assertEqual(answer.count("/api/v1/nodes/"), 2)
        self.assertIn("http://api.test/api/v1/nodes/", answer)
        self.assertIn("**Источники:**", answer)

    def test_reasoning_filter_and_context_fallback(self):
        self.assertEqual(
            remove_reasoning_leak("Analysis: private reasoning\nFinal answer: Rule applies."),
            "Rule applies.",
        )
        self.assertIsNone(remove_reasoning_leak("Analysis: no final answer"))
        match = RetrievedMatch(
            node_ids=(str(uuid4()),),
            text=(
                "Breadcrumbs: Закон > Статья 1\nТекст фрагмента:\n"
                "1. Первое предложение. Второе предложение."
            ),
            score=1.0,
        )
        self.assertEqual(
            context_answer_fallback([match]),
            "Первое предложение.\n\nИсточник: Закон > Статья 1",
        )

    def test_followup_query_uses_previous_question(self):
        self.assertEqual(
            build_retrieval_query(
                "А статья 10?", [{"role": "user", "content": "Какие есть основания?"}]
            ),
            "Какие есть основания?\nА статья 10?",
        )
        self.assertEqual(build_retrieval_query("Свежий вопрос", []), "Свежий вопрос")

    def test_only_free_openrouter_models_are_allowed(self):
        self.assertEqual(require_free_model("sample:free", "MODEL"), "sample:free")
        with self.assertRaisesRegex(RuntimeError, "paid model IDs are disabled"):
            require_free_model("sample:paid", "MODEL")


class TestQueryAsync(unittest.IsolatedAsyncioTestCase):
    async def test_search_fuses_vector_and_bm25_results_by_node(self):
        node_id = uuid4()
        session = FakeSession(
            [
                [(True, True)],
                [(node_id, "vector excerpt", ["Law", "Article 1"], "Article 1", "Law")],
                [(node_id, "Article 1", ["Law", "Article 1"], "full article", "Law")],
            ]
        )
        with patch(
            "app.services.query.search_chunks.session_factory",
            return_value=SessionContext(session),
        ):
            matches = await search_chunks([0.1, 0.2], "general query")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].node_ids, (str(node_id),))
        self.assertIn("full article", matches[0].text)
        self.assertGreater(matches[0].score, 0)

    async def test_search_keeps_vector_results_when_bm25_is_unavailable(self):
        node_id = uuid4()
        session = FakeSession(
            [
                [(True, True)],
                [(node_id, "vector excerpt", ["Law"], "Title", "Law")],
                SQLAlchemyError("BM25 extension unavailable"),
            ]
        )
        with patch(
            "app.services.query.search_chunks.session_factory",
            return_value=SessionContext(session),
        ):
            with self.assertLogs("app.services.query.search_chunks", level="ERROR"):
                matches = await search_chunks([0.1], "general query")

        self.assertEqual(len(matches), 1)
        self.assertTrue(session.rolled_back)

    async def test_search_adds_exact_article_matches_for_article_queries(self):
        node_id = uuid4()
        session = FakeSession(
            [
                [(True, True)],
                [],
                [],
                [
                    (
                        node_id,
                        "Статья 48. Воинская обязанность",
                        ["Федеральный закон", "Статья 48. Воинская обязанность"],
                        "Article body",
                        "Law",
                    )
                ],
            ]
        )
        with patch(
            "app.services.query.search_chunks.session_factory",
            return_value=SessionContext(session),
        ):
            matches = await search_chunks([0.1], "Что предусмотрено в статье 48?")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].node_ids, (str(node_id),))
        self.assertIn("Article body", matches[0].text)

    async def test_openrouter_rerank_applies_top_k(self):
        matches = [RetrievedMatch((str(uuid4()),), f"Passage {i}", float(i)) for i in range(3)]

        def handler(request):
            self.assertEqual(request.url.path, "/api/v1/rerank")
            return httpx.Response(
                200,
                json={"results": [{"index": 2}, {"index": 0}, {"index": 1}]},
            )

        with (
            patch.object(query_settings, "rerank_provider", "openrouter"),
            patch.object(query_settings, "openrouter_rerank_model", "reranker:free"),
            patch.object(query_settings, "top_k", 2),
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                reranked = await rerank_chunks(client, "api-key", "question", matches)

        self.assertEqual([match.text for match in reranked], ["Passage 2", "Passage 0"])

    async def test_ollama_rerank_orders_candidates_and_caps_results(self):
        matches = [RetrievedMatch((str(uuid4()),), f"Passage {i}", float(i)) for i in range(3)]

        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["model"], "test-reranker")
            return httpx.Response(
                200,
                json={"message": {"content": json.dumps({"ranking": [2, 0, 1]})}},
            )

        with (
            patch.object(query_settings, "ollama_base_url", "http://ollama.test"),
            patch.object(query_settings, "ollama_rerank_model", "test-reranker"),
            patch.object(query_settings, "top_k", 2),
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                reranked = await rerank_chunks_with_ollama(client, "query", matches)

        self.assertEqual([match.text for match in reranked], ["Passage 2", "Passage 0"])

    async def test_openrouter_answer_uses_context_and_cleans_analysis(self):
        match = RetrievedMatch((str(uuid4()),), "Breadcrumbs: Law", 1.0)

        def handler(request):
            payload = json.loads(request.content)
            self.assertIn("Retrieved context", payload["messages"][0]["content"])
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "Analysis: hidden\nFinal answer: Grounded."}}
                    ]
                },
            )

        with (
            patch.object(query_settings, "query_llm_provider", "openrouter"),
            patch.object(query_settings, "openrouter_chat_model", "chat:free"),
            patch.object(query_settings, "openrouter_chat_fallback_models", ""),
            patch.object(query_settings, "openrouter_url", "http://router.test/v1"),
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                answer = await generate_answer(client, "key", "Question", [], [match])

        self.assertEqual(answer, "Grounded.")

    async def test_ollama_answer_uses_http_service(self):
        match = RetrievedMatch((str(uuid4()),), "Breadcrumbs: Law", 1.0)

        def handler(request):
            self.assertEqual(request.url.path, "/api/chat")
            self.assertEqual(json.loads(request.content)["model"], "test-chat")
            return httpx.Response(
                200,
                json={"message": {"content": "Grounded answer."}},
            )

        with (
            patch.object(query_settings, "ollama_base_url", "http://ollama.test"),
            patch.object(query_settings, "ollama_model", "test-chat"),
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                answer = await generate_answer_with_ollama(
                    client,
                    [{"role": "user", "content": "Question"}],
                    [match],
                )

        self.assertEqual(answer, "Grounded answer.")


if __name__ == "__main__":
    unittest.main()
