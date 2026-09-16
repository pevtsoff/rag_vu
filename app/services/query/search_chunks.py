"""Retrieve and fuse semantic, BM25, and exact article matches."""

import logging
import re
from uuid import UUID

import httpx
from sqlalchemy import Text, cast, event, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import AsyncSessionLocal, engine
from app.models import Chunk, Document, Node
from app.services.embeddings import create_embeddings, embedding_column_name
from app.services.query.exceptions import BM25SearchUnavailableError
from app.services.query.retrieve_context import (
    build_retrieved_context,
    format_breadcrumbs,
    retrieve_article_context,
)
from app.services.query.settings import settings as query_settings
from app.services.query.types import RetrievedMatch

session_factory = AsyncSessionLocal


def log_sql_query(connection, cursor, statement, parameters, context, executemany):
    """Log SQL without printing potentially large bound vector values."""
    logging.getLogger("app.services.query.sql").info("Executing SQL:\n%s", statement)


event.listen(engine.sync_engine, "before_cursor_execute", log_sql_query)


def _get_bm25_index_name() -> str:
    """Get the BM25 index name from the Node SQLAlchemy model."""
    for index in Node.__table__.indexes:
        if index.dialect_options["postgresql"].get("using") == "bm25":
            return index.name
    raise BM25SearchUnavailableError(
        "BM25 search is unavailable: Node model has no PostgreSQL BM25 index declared."
    )


async def _ensure_pg_textsearch_and_bm25_available(session) -> str:
    """Fail early unless pg_textsearch and the model's BM25 index are ready."""
    index_name = _get_bm25_index_name()
    result = await session.execute(
        text(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_textsearch'
                ),
                EXISTS (
                    SELECT 1
                    FROM pg_class AS index_class
                    JOIN pg_index AS index_info
                      ON index_info.indexrelid = index_class.oid
                    JOIN pg_am AS access_method
                      ON access_method.oid = index_class.relam
                    WHERE index_class.oid = to_regclass(:index_name)
                      AND access_method.amname = 'bm25'
                      AND index_info.indisvalid
                )
            """
        ),
        {"index_name": index_name},
    )
    extension_installed, index_ready = result.first()
    if not extension_installed or not index_ready:
        missing = []
        if not extension_installed:
            missing.append("pg_textsearch extension")
        if not index_ready:
            missing.append(f"valid {index_name} BM25 index")
        raise BM25SearchUnavailableError(
            f"BM25 search is unavailable: missing {', '.join(missing)}. "
            "Apply the database migration and verify the PostgreSQL extension setup."
        )
    return index_name


async def embed_query(
    client: httpx.AsyncClient, query: str, api_key: str | None = None
) -> list[float]:
    """Embed a search query with the same provider and dimensions as chunking."""
    return (
        await create_embeddings(
            client=client,
            texts=[query],
            task="query",
            api_key=api_key,
        )
    )[0]


async def search_chunks(query_embedding: list[float], query: str = "") -> list[RetrievedMatch]:
    """Retrieve vector and BM25 candidates, then combine their rankings with RRF."""
    embedding_column = getattr(Chunk, embedding_column_name())
    distance = embedding_column.cosine_distance(query_embedding).label("distance")
    vector_statement = (
        select(
            Chunk.node_id,
            Chunk.text,
            Node.breadcrumbs,
            Node.title,
            Document.file_name,
        )
        .join(Node, Node.id == Chunk.node_id)
        .join(Document, Document.id == Node.document_id)
        .where(
            embedding_column.is_not(None),
            Node.node_type.in_(("article", "article_part", "section", "preamble", "header")),
        )
        .order_by(distance)
        # Several nearby chunk vectors can belong to the same article part.
        # Fetch extra rows, then keep the best chunk per node below.
        .limit(query_settings.retrieval_candidate_k * 5)
    )

    async with session_factory() as session:
        bm25_index_name = await _ensure_pg_textsearch_and_bm25_available(session)
        result = await session.execute(vector_statement)
        vector_matches: list[tuple[str, str]] = []
        vector_node_ids = set()
        for node_id, text, breadcrumbs, title, file_name in result.all():
            if node_id in vector_node_ids:
                continue
            vector_node_ids.add(node_id)
            vector_matches.append(
                (
                    f"node:{node_id}",
                    build_retrieved_context(text, breadcrumbs, title, file_name),
                )
            )
            if len(vector_matches) >= query_settings.retrieval_candidate_k:
                break

        bm25_matches: list[tuple[str, str]] = []
        # An explicit index name makes the query work with prepared SQL.
        bm25_query = func.to_bm25query(query, bm25_index_name)
        bm25_score = Node.text.op("<@>")(bm25_query)
        bm25_statement = (
            select(
                Node.id,
                Node.title,
                Node.breadcrumbs,
                Node.text,
                Document.file_name,
            )
            .join(Document, Document.id == Node.document_id)
            .where(
                Node.text.is_not(None),
                Node.node_type.in_(
                    ("article", "article_part", "section", "preamble", "header")
                ),
            )
            .order_by(bm25_score)
            .limit(query_settings.retrieval_candidate_k)
        )
        try:
            result = await session.execute(bm25_statement)
        except SQLAlchemyError:
            logging.getLogger(__name__).exception(
                "BM25 retrieval failed; pg_textsearch and idx_nodes_text_bm25 are required."
            )
            await session.rollback()
        else:
            for node_id, title, breadcrumbs, text, file_name in result.all():
                context = build_retrieved_context(text, breadcrumbs, title, file_name)
                bm25_matches.append((f"node:{node_id}", context))

        # Article numbers are identifiers, not concepts. Embeddings alone often
        # rank unrelated laws for questions such as “what does Article 48 say?”.
        article = re.search(
            r"\b(?:стать[еяи]|ст\.)\s*(\d+(?:\.\d+)?)\b",
            query,
            re.IGNORECASE,
        )
        article_matches: list[tuple[str, str]] = []
        if article:
            number = article.group(1)
            exact_article = re.compile(rf"Статья\s+{re.escape(number)}(?!\d|\.\d)", re.IGNORECASE)
            article_statement = (
                select(
                    Node.id,
                    Node.title,
                    Node.breadcrumbs,
                    Node.text,
                    Document.file_name,
                )
                .join(Document, Document.id == Node.document_id)
                .where(
                    Node.node_type.in_(("article", "article_part")),
                    or_(
                        Node.title.ilike(f"%Статья {number}%"),
                        cast(Node.breadcrumbs, Text).ilike(f"%Статья {number}%"),
                        Node.text.ilike(f"%Статья {number}%"),
                    ),
                )
                .order_by(Node.path)
                .limit(query_settings.retrieval_candidate_k)
            )
            result = await session.execute(article_statement)
            for node_id, title, breadcrumbs, text, file_name in result.all():
                hierarchy = format_breadcrumbs(breadcrumbs)
                context = build_retrieved_context(text, breadcrumbs, title, file_name)
                if exact_article.search(f"{hierarchy} {title or ''}"):
                    article_matches.append((f"node:{node_id}", context))

    # Fuse vector and BM25 rankings by node ID, so a node found by both sources
    # receives a combined score instead of appearing twice as chunk:<id>/node:<id>.
    ranked: dict[str, dict[str, object]] = {}
    for source_matches in (vector_matches, bm25_matches, article_matches):
        for rank, (node_key, text) in enumerate(source_matches, start=1):
            item = ranked.setdefault(
                node_key,
                {
                    "text": text,
                    "score": 0.0,
                    "node_ids": [node_key.removeprefix("node:")],
                },
            )
            item["score"] = float(item["score"]) + 1.0 / (query_settings.rrf_k + rank)
            # BM25 carries the full article-part text, while vector retrieval
            # carries the nearest chunk excerpt. Prefer the full text on overlap.
            if source_matches is bm25_matches:
                item["text"] = text

    best = sorted(ranked.items(), key=lambda pair: float(pair[1]["score"]), reverse=True)

    # Questions asking for a list need article coverage, not just the single
    # highest-scoring paragraph. Add the complete parent article when one of
    # the leading results belongs to an article split into numbered parts.
    asks_for_list = bool(
        re.search(
            r"\b(?:какие|перечисл(?:и|ите)|список|перечень|основани[ея]|"
            r"все\s+основания)\b",
            query,
            re.IGNORECASE,
        )
    )
    if asks_for_list:
        seed_keys = [key for key, _ in best if key.startswith("node:")][:10]
        try:
            seed_ids = [UUID(key.removeprefix("node:")) for key in seed_keys]
        except ValueError:
            seed_ids = []

        if seed_ids:
            async with session_factory() as session:
                seed_result = await session.execute(
                    select(Node.id, Node.document_id, Node.path, Node.node_type).where(
                        Node.id.in_(seed_ids),
                        Node.node_type.in_(("article", "article_part")),
                    )
                )
                seed_nodes = {
                    node_id: (document_id, str(path), node_type)
                    for node_id, document_id, path, node_type in seed_result.all()
                    if path
                }
                for key in seed_keys:
                    node_id = UUID(key.removeprefix("node:"))
                    seed = seed_nodes.get(node_id)
                    if not seed:
                        continue
                    document_id, seed_path, node_type = seed
                    article_path = (
                        seed_path.rsplit(".", maxsplit=1)[0]
                        if node_type == "article_part"
                        else seed_path
                    )
                    article_context = await retrieve_article_context(
                        session, document_id, article_path
                    )
                    if not article_context:
                        continue
                    article_text, source_node_ids = article_context

                    ranked[f"article:{document_id}:{article_path}"] = {
                        "text": article_text,
                        "node_ids": source_node_ids,
                        # Keep the complete article in the bounded rerank pool;
                        # if reranking fails, it also leads the hybrid fallback.
                        "score": 1.0,
                    }
                    break
            best = sorted(
                ranked.items(),
                key=lambda pair: float(pair[1]["score"]),
                reverse=True,
            )

    return [
        RetrievedMatch(
            node_ids=tuple(item["node_ids"]),
            text=str(item["text"]),
            score=float(item["score"]),
        )
        for _, item in best[: query_settings.rerank_candidate_k]
    ]
