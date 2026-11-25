"""Hybrid retrieval: pgvector similarity + BM25 + exact article numbers, fused by RRF."""

import logging
import re
from collections.abc import Awaitable
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.outbound.persistence.vector_columns import vector_column_for
from app.adapters.outbound.retrieval.bm25_availability import ensure_bm25_available
from app.adapters.outbound.retrieval.candidate_queries import (
    article_candidates,
    bm25_candidates,
    vector_candidates,
    version_rows,
)
from app.adapters.outbound.retrieval.list_question_expander import (
    ListQuestionExpander,
    asks_for_list,
)
from app.adapters.outbound.retrieval.rank_fusion import best_first, fuse_rankings
from app.adapters.outbound.retrieval.ranked_candidate import RankedCandidate
from app.adapters.outbound.retrieval.retrieval_limits import RetrievalLimits
from app.adapters.outbound.retrieval.version_selection import select_versions
from app.application.ports.retriever import Retriever
from app.application.ports.tracer import Tracer
from app.application.tracing.document_role import DocumentRole
from app.application.tracing.match_documents import ranked_documents
from app.application.tracing.null_tracer import NullTracer
from app.application.tracing.span_kind import SpanKind
from app.application.tracing.trace_attributes import (
    RETRIEVAL_CANDIDATE_COUNT,
    RETRIEVAL_SOURCE,
)
from app.application.use_cases.query.retrieved_context import (
    build_retrieved_context,
    format_breadcrumbs,
    retrieved_passage,
)
from app.application.use_cases.query.version_question import named_versions
from app.domain.retrieval.match_version import MatchVersion
from app.domain.retrieval.retrieved_match import RetrievedMatch
from app.domain.versioning.text_normalization import content_hash

logger = logging.getLogger(__name__)
ARTICLE_REFERENCE = re.compile(r"\b(?:стать[еяи]|ст\.)\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)
VECTOR_OVERFETCH = 5
DEFAULT_TRACED_K = 5


class SqlAlchemyHybridRetriever(Retriever):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        limits: RetrievalLimits,
        tracer: Tracer | None = None,
        traced_k: int = DEFAULT_TRACED_K,
    ) -> None:
        """``traced_k`` caps how many candidates of each source are recorded on its span."""
        self._session_factory = session_factory
        self._limits = limits
        self._tracer = tracer or NullTracer()
        self._traced_k = traced_k

    async def retrieve(
        self, query_vector: list[float], query: str, latest_only: bool = True
    ) -> list[RetrievedMatch]:
        async with self._session_factory() as session:
            ranked = await self._ranked(session, query_vector, query, latest_only)
            versions = await _versions(session, ranked)
        versioned = [(item, versions.get(item.node_ids[0])) for _, item in ranked if item.node_ids]
        if not latest_only:
            versioned = select_versions(versioned, self._limits, named_versions(query))
        return [_match(item, version) for item, version in versioned][
            : self._limits.rerank_candidate_k
        ]

    async def _ranked(
        self, session: AsyncSession, query_vector: list[float], query: str, latest_only: bool
    ) -> list[tuple[str, RankedCandidate]]:
        index_name = await ensure_bm25_available(session)
        k = self._limits.candidates(latest_only)
        sources = [
            await self._traced(
                "vector", query, self._vector(session, query_vector, k, latest_only)
            ),
            await self._traced(
                "bm25", query, self._bm25(session, query, index_name, k, latest_only)
            ),
            await self._traced("article", query, self._articles(session, query, k, latest_only)),
        ]
        ranked = best_first(fuse_rankings(sources, self._limits.rrf_k))
        if asks_for_list(query):
            ranked = best_first(
                {**dict(ranked), **await ListQuestionExpander(session).expand(ranked)}
            )
        return ranked

    async def _traced(
        self, source: str, query: str, matches: Awaitable[list[tuple[str, str]]]
    ) -> tuple[str, list[tuple[str, str]]]:
        """Run one retrieval source inside its own RETRIEVER span."""
        with self._tracer.span(f"retrieval.{source}", SpanKind.RETRIEVER) as span:
            span.set_input(query)
            span.set_top_k(self._traced_k)
            found = await matches
            span.set_attributes({RETRIEVAL_SOURCE: source, RETRIEVAL_CANDIDATE_COUNT: len(found)})
            span.set_documents(
                DocumentRole.RETRIEVED, ranked_documents(source, found[: self._traced_k])
            )
            return source, found

    async def _vector(
        self, session: AsyncSession, query_vector: list[float], k: int, latest_only: bool
    ) -> list[tuple[str, str]]:
        # Several chunks can belong to one node: over-fetch, then keep the best per node.
        column = vector_column_for(len(query_vector))
        statement = vector_candidates(column, query_vector, k * VECTOR_OVERFETCH, latest_only)
        rows = (await session.execute(statement)).all()
        matches: dict[str, str] = {}
        for node_id, text, breadcrumbs, title, file_name in rows:
            key = f"node:{node_id}"
            if key not in matches:
                matches[key] = build_retrieved_context(text, breadcrumbs, title, file_name)
        return list(matches.items())[:k]

    async def _bm25(
        self, session: AsyncSession, query: str, index_name: str, k: int, latest_only: bool
    ) -> list[tuple[str, str]]:
        try:
            result = await session.execute(bm25_candidates(query, index_name, k, latest_only))
        except SQLAlchemyError:
            logger.exception("BM25 retrieval failed; pg_textsearch and its index are required.")
            await session.rollback()
            return []
        return [_node_match(row) for row in result.all()]

    async def _articles(
        self, session: AsyncSession, query: str, k: int, latest_only: bool
    ) -> list[tuple[str, str]]:
        """Article numbers are identifiers, which embeddings match poorly."""
        reference = ARTICLE_REFERENCE.search(query)
        if not reference:
            return []
        number = reference.group(1)
        exact = re.compile(rf"Статья\s+{re.escape(number)}(?!\d|\.\d)", re.IGNORECASE)
        rows = (await session.execute(article_candidates(number, k, latest_only))).all()
        return [
            _node_match(row)
            for row in rows
            if exact.search(f"{format_breadcrumbs(row[2])} {row[1] or ''}")
        ]


async def _versions(
    session: AsyncSession, ranked: list[tuple[str, RankedCandidate]]
) -> dict[str, MatchVersion]:
    """The document version of each candidate's first node, for labels and version grouping."""
    first_nodes = {item.node_ids[0]: item for _, item in ranked if item.node_ids}
    if not first_nodes:
        return {}
    rows = (await session.execute(version_rows(list(first_nodes)))).all()
    return {str(row[0]): _version(row, first_nodes[str(row[0])].text) for row in rows}


def _version(row: Any, text: str) -> MatchVersion:
    _, document_id, cluster_id, version, is_latest, file_name, created_at, redaction = row
    return MatchVersion(
        document_id=str(document_id),
        cluster_id=str(cluster_id),
        version=version,
        is_latest=is_latest,
        file_name=file_name,
        created_at=created_at,
        redaction=redaction,
        content_hash=content_hash(retrieved_passage(text)),
    )


def _match(item: RankedCandidate, version: MatchVersion | None) -> RetrievedMatch:
    return RetrievedMatch(tuple(item.node_ids), item.text, item.score, version)


def _node_match(row: Any) -> tuple[str, str]:
    node_id, title, breadcrumbs, text, file_name = row
    return f"node:{node_id}", build_retrieved_context(text, breadcrumbs, title, file_name)
