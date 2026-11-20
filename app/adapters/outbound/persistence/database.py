"""Engine and session factory construction."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def create_engine(url: str, null_pool: bool = False, echo: bool = False) -> AsyncEngine:
    """Use ``null_pool`` where each job runs in a fresh event loop (Celery workers)."""
    if null_pool:
        return create_async_engine(url, echo=echo, poolclass=NullPool)
    return create_async_engine(url, echo=echo, pool_size=20, max_overflow=10, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
