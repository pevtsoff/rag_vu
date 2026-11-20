"""Hybrid retrieval: pgvector similarity + BM25 + exact article numbers, fused by RRF."""

import logging
import re
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.outbound.persistence.vector_columns import vector_column_for
from app.adapters.outbound.retrieval.bm25_availability import ensure_bm25_available
from app.adapters.outbound.retrieval.candidate_queries import (
    article_candidates,
    bm25_candidates,
    vector_candidates,
)
from app.adapters.outbound.retrieval.list_question_expander import (
    ListQuestionExpander,
    asks_for_list,
)
from app.adapters.outbound.retrieval.rank_fusion import best_first, fuse_rankings
from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.application.ports.retriever import Retriever
from app.application.use_cases.query.retrieved_context import (
    build_retrieved_context,
    format_breadcrumbs,
)
from app.domain.retrieval.retrieved_match import RetrievedMatch

logger = logging.getLogger(__name__)
ARTICLE_REFERENCE = re.compile(r"\b(?:стать[еяи]|ст\.)\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)
VECTOR_OVERFETCH = 5


class SqlAlchemyHybridRetriever(Retriever):
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], limits: RetrievalLimits
    ) -> None:
        self._session_factory = session_factory
        self._limits = limits

    async def retrieve(self, query_vector: list[float], query: str) -> list[RetrievedMatch]:
        async with self._session_factory() as session:
            index_name = await ensure_bm25_available(session)
            sources = [
                ("vector", await self._vector(session, query_vector)),
                ("bm25", await self._bm25(session, query, index_name)),
                ("article", await self._articles(session, query)),
            ]
            ranked = best_first(fuse_rankings(sources, self._limits.rrf_k))
            if asks_for_list(query):
                ranked = best_first(
                    {**dict(ranked), **await ListQuestionExpander(session).expand(ranked)}
                )
        return [
            RetrievedMatch(tuple(item.node_ids), item.text, item.score)
            for _, item in ranked[: self._limits.rerank_candidate_k]
        ]

    async def _vector(
        self, session: AsyncSession, query_vector: list[float]
    ) -> list[tuple[str, str]]:
        # Several chunks can belong to one node: over-fetch, then keep the best per node.
        column = vector_column_for(len(query_vector))
        limit = self._limits.candidate_k * VECTOR_OVERFETCH
        rows = (await session.execute(vector_candidates(column, query_vector, limit))).all()
        matches: dict[str, str] = {}
        for node_id, text, breadcrumbs, title, file_name in rows:
            key = f"node:{node_id}"
            if key not in matches:
                matches[key] = build_retrieved_context(text, breadcrumbs, title, file_name)
        return list(matches.items())[: self._limits.candidate_k]

    async def _bm25(
        self, session: AsyncSession, query: str, index_name: str
    ) -> list[tuple[str, str]]:
        try:
            result = await session.execute(
                bm25_candidates(query, index_name, self._limits.candidate_k)
            )
        except SQLAlchemyError:
            logger.exception("BM25 retrieval failed; pg_textsearch and its index are required.")
            await session.rollback()
            return []
        return [_node_match(row) for row in result.all()]

    async def _articles(self, session: AsyncSession, query: str) -> list[tuple[str, str]]:
        """Article numbers are identifiers, which embeddings match poorly."""
        reference = ARTICLE_REFERENCE.search(query)
        if not reference:
            return []
        number = reference.group(1)
        exact = re.compile(rf"Статья\s+{re.escape(number)}(?!\d|\.\d)", re.IGNORECASE)
        rows = (await session.execute(article_candidates(number, self._limits.candidate_k))).all()
        return [
            _node_match(row)
            for row in rows
            if exact.search(f"{format_breadcrumbs(row[2])} {row[1] or ''}")
        ]


def _node_match(row: Any) -> tuple[str, str]:
    node_id, title, breadcrumbs, text, file_name = row
    return f"node:{node_id}", build_retrieved_context(text, breadcrumbs, title, file_name)
