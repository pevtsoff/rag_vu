"""Database connection settings for the chunking service."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CHUNKING_DATABASE_URL = "postgresql+asyncpg://rag_vu_user:rag_vu_password@localhost:8432/rag_vu_db"


def create_database_session_factory():
    """Create the async engine and session factory used by chunking."""
    engine = create_async_engine(CHUNKING_DATABASE_URL, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory
