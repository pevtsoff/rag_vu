"""Answer a question from retrieved, reranked passages."""

from app.application.errors import AnswerGenerationError
from app.application.ports.chat_model import ChatModel
from app.application.ports.embedder import Embedder
from app.application.ports.reranker import Reranker
from app.application.ports.retriever import Retriever
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
    ) -> None:
        self._embedder = embedder
        self._retriever = retriever
        self._reranker = reranker
        self._chat_model = chat_model
        self._api_base_url = api_base_url
        self._max_history_turns = max_history_turns

    async def execute(self, question: str, history: list[dict[str, str]]) -> str:
        retrieval_query = build_retrieval_query(question, history)
        matches = await self._matches(retrieval_query)
        messages = build_answer_messages(question, history, matches, self._max_history_turns)
        answer = remove_reasoning_leak(await self._chat_model.complete(messages))
        if not answer:
            raise AnswerGenerationError("The chat model returned reasoning without a final answer.")
        return append_source_links(answer, matches, self._api_base_url)

    async def _matches(self, retrieval_query: str) -> list[RetrievedMatch]:
        vectors = await self._embedder.embed([retrieval_query], EmbeddingTask.QUERY)
        candidates = await self._retriever.retrieve(vectors[0], retrieval_query)
        return await self._reranker.rerank(retrieval_query, candidates)
