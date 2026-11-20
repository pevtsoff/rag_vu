"""Fail fast unless pg_textsearch and the BM25 index on ``nodes.text`` are ready."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.models.node_model import BM25_INDEX_NAME
from app.adapters.outbound.retrieval.bm25_unavailable_error import Bm25UnavailableError

_AVAILABILITY_SQL = text(
    """
    SELECT
        EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_textsearch'),
        EXISTS (
            SELECT 1
            FROM pg_class AS index_class
            JOIN pg_index AS index_info ON index_info.indexrelid = index_class.oid
            JOIN pg_am AS access_method ON access_method.oid = index_class.relam
            WHERE index_class.oid = to_regclass(:index_name)
              AND access_method.amname = 'bm25'
              AND index_info.indisvalid
        )
    """
)


async def ensure_bm25_available(session: AsyncSession) -> str:
    """Return the BM25 index name; raise Bm25UnavailableError when it cannot be used."""
    result = await session.execute(_AVAILABILITY_SQL, {"index_name": BM25_INDEX_NAME})
    extension_installed, index_ready = result.first()
    missing = []
    if not extension_installed:
        missing.append("pg_textsearch extension")
    if not index_ready:
        missing.append(f"valid {BM25_INDEX_NAME} BM25 index")
    if missing:
        raise Bm25UnavailableError(
            f"BM25 search is unavailable: missing {', '.join(missing)}. "
            "Apply the database migration and verify the PostgreSQL extension setup."
        )
    return BM25_INDEX_NAME
