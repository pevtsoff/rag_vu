"""Flushing that reports uniqueness races as application conflicts."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.errors import ConcurrencyConflictError


async def flush_or_conflict(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConcurrencyConflictError(str(exc.orig)) from exc


async def commit_or_conflict(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConcurrencyConflictError(str(exc.orig)) from exc
