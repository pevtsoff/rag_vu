"""Retrieval and answering, used by the chat UI and the search endpoint."""

from functools import cached_property

from app.adapters.outbound.llm.free_model_policy import free_model_chain, require_free_model
from app.adapters.outbound.llm.ollama_chat_model import OllamaChatModel
from app.adapters.outbound.llm.openrouter_chat_model import OpenRouterChatModel
from app.adapters.outbound.rerank.fallback_reranker import FallbackReranker
from app.adapters.outbound.rerank.local_reranker import LocalReranker
from app.adapters.outbound.rerank.ollama_reranker import OllamaReranker
from app.adapters.outbound.rerank.openrouter_reranker import OpenRouterReranker
from app.adapters.outbound.rerank.passthrough_reranker import PassthroughReranker
from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.adapters.outbound.retrieval.sqlalchemy_hybrid_retriever import SqlAlchemyHybridRetriever
from app.application.ports.chat_model import ChatModel
from app.application.ports.reranker import Reranker
from app.application.ports.retriever import Retriever
from app.application.ports.tracer import Tracer
from app.application.tracing.traced_chat_model import TracedChatModel
from app.application.tracing.traced_reranker import TracedReranker
from app.application.tracing.traced_retriever import TracedRetriever
from app.application.use_cases.query.answer_question import AnswerQuestion
from app.bootstrap.infrastructure import Infrastructure

PASSTHROUGH_RERANK_MODEL = "passthrough"


class QueryContainer:
    def __init__(self, infrastructure: Infrastructure) -> None:
        self.infrastructure = infrastructure
        self._settings = infrastructure.settings

    @property
    def _tracer(self) -> Tracer:
        return self.infrastructure.tracer

    @cached_property
    def retriever(self) -> Retriever:
        settings = self._settings
        limits = RetrievalLimits(
            settings.retrieval_candidate_k,
            settings.rerank_candidate_k,
            settings.rrf_k,
            settings.multi_version_overfetch,
            settings.k_per_version,
            settings.version_relevance_floor,
            settings.max_versions,
        )
        hybrid = SqlAlchemyHybridRetriever(
            self.infrastructure.session_factory, limits, self._tracer, self._settings.top_k
        )
        return TracedRetriever(hybrid, self._tracer)

    @cached_property
    def reranker(self) -> Reranker:
        reranker, model_name = self._provider_reranker()
        return TracedReranker(reranker, self._tracer, model_name, self._settings.top_k)

    def _provider_reranker(self) -> tuple[Reranker, str]:
        settings = self._settings
        provider = settings.rerank_provider.strip().lower()
        clients = self.infrastructure.http_client_factory
        if provider == "ollama":
            model = settings.ollama_rerank_model
            inner = OllamaReranker(clients, settings.ollama_base_url, model, settings.top_k)
        elif provider == "local":
            model = "local/qwen3-reranker-0.6b"
            inner = LocalReranker(clients, settings.local_reranker_base_url, settings.top_k)
        elif provider != "openrouter":
            raise ValueError("RERANK_PROVIDER must be 'ollama', 'openrouter' or 'local'.")
        elif not settings.openrouter_api_key:
            return PassthroughReranker(settings.top_k), PASSTHROUGH_RERANK_MODEL
        else:
            model = require_free_model(settings.openrouter_rerank_model, "OPENROUTER_RERANK_MODEL")
            inner = OpenRouterReranker(
                clients, settings.openrouter_url, settings.openrouter_api_key, model, settings.top_k
            )
        return FallbackReranker(inner, settings.top_k), model

    @cached_property
    def chat_model(self) -> ChatModel:
        return TracedChatModel(self._provider_chat_model(), self._tracer)

    def _provider_chat_model(self) -> ChatModel:
        settings = self._settings
        provider = settings.query_llm_provider.strip().lower()
        clients = self.infrastructure.http_client_factory
        if provider == "ollama":
            return OllamaChatModel(
                clients,
                settings.ollama_base_url,
                settings.ollama_model,
                settings.ollama_timeout_seconds,
                settings.ollama_max_answer_tokens,
            )
        if provider != "openrouter":
            raise ValueError("QUERY_LLM_PROVIDER must be 'ollama' or 'openrouter'.")
        chain = free_model_chain(
            settings.openrouter_chat_model, settings.openrouter_chat_fallback_models
        )
        return OpenRouterChatModel(
            clients, settings.openrouter_url, settings.openrouter_api_key, chain
        )

    @cached_property
    def answer_question(self) -> AnswerQuestion:
        return AnswerQuestion(
            self.infrastructure.embedder,
            self.retriever,
            self.reranker,
            self.chat_model,
            self._settings.rag_vu_api_base_url,
            self._settings.max_history_turns,
            self._tracer,
            self._settings.multi_version_chunk_budget,
        )
