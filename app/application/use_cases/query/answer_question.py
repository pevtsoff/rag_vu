"""Answer a question from retrieved, reranked passages."""

from app.application.errors import AnswerGenerationError
from app.application.ports.chat_model import ChatModel
from app.application.ports.embedder import Embedder
from app.application.ports.reranker import Reranker
from app.application.ports.retriever import Retriever
from app.application.ports.trace_span import TraceSpan
from app.application.ports.tracer import Tracer
from app.application.tracing.null_tracer import NullTracer
from app.application.tracing.trace_attributes import (
    QUERY_CONTEXT_CHARS,
    QUERY_HISTORY_MESSAGES,
    QUERY_REASONING_REMOVED,
    QUERY_RETRIEVAL_QUERY,
    QUERY_REWRITTEN,
    QUERY_SOURCE_COUNT,
)
from app.application.use_cases.query.answer_prompt import build_answer_messages
from app.application.use_cases.query.reasoning_filter import remove_reasoning_leak
from app.application.use_cases.query.retrieval_query import build_retrieval_query
from app.application.use_cases.query.source_links import append_source_links
from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.retrieval.retrieved_match import RetrievedMatch


class AnswerQuestion:
    def __init__(
        self,
        embedder: Embedder,
        retriever: Retriever,
        reranker: Reranker,
        chat_model: ChatModel,
        api_base_url: str,
        max_history_turns: int,
        tracer: Tracer | None = None,
    ) -> None:
        self._embedder = embedder
        self._retriever = retriever
        self._reranker = reranker
        self._chat_model = chat_model
        self._api_base_url = api_base_url
        self._max_history_turns = max_history_turns
        self._tracer = tracer or NullTracer()

    async def execute(
        self, question: str, history: list[dict[str, str]], session_id: str | None = None
    ) -> str:
        """Answer ``question``; ``session_id`` groups the traces of one conversation."""
        with self._tracer.span("rag.query") as span:
            span.set_input(question)
            if session_id:
                span.set_session(session_id)
            answer = await self._answer(question, history, span)
            span.set_output(answer)
            return answer

    async def _answer(self, question: str, history: list[dict[str, str]], span: TraceSpan) -> str:
        retrieval_query = build_retrieval_query(question, history)
        span.set_attributes(
            {
                QUERY_HISTORY_MESSAGES: len(history),
                QUERY_RETRIEVAL_QUERY: retrieval_query,
                QUERY_REWRITTEN: retrieval_query != question,
            }
        )
        matches = await self._matches(retrieval_query)
        messages = build_answer_messages(question, history, matches, self._max_history_turns)
        span.set_attributes(
            {
                QUERY_SOURCE_COUNT: len(matches),
                QUERY_CONTEXT_CHARS: sum(len(match.text) for match in matches),
            }
        )
        answer = await self._final_answer(messages, span)
        return append_source_links(answer, matches, self._api_base_url)

    async def _final_answer(self, messages: list[dict[str, str]], span: TraceSpan) -> str:
        raw = (await self._chat_model.complete(messages)).text
        answer = remove_reasoning_leak(raw)
        span.set_attributes({QUERY_REASONING_REMOVED: answer != raw.strip()})
        if not answer:
            raise AnswerGenerationError("The chat model returned reasoning without a final answer.")
        return answer

    async def _matches(self, retrieval_query: str) -> list[RetrievedMatch]:
        vectors = await self._embedder.embed([retrieval_query], EmbeddingTask.QUERY)
        candidates = await self._retriever.retrieve(vectors[0], retrieval_query)
        return await self._reranker.rerank(retrieval_query, candidates)
