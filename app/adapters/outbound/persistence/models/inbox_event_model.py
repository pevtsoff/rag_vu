import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.adapters.outbound.persistence.models.base import Base

INBOX_UNIQUE_CONSTRAINT = "uq_inbox_events_event_consumer"


class InboxEventModel(Base):
    """One row per (event, consumer); the unique pair makes delivery idempotent."""

    __tablename__ = "inbox_events"
    __table_args__ = (
        UniqueConstraint("event_id", "consumer", name=INBOX_UNIQUE_CONSTRAINT),
        Index("ix_inbox_events_status_dispatched_at", "status", "dispatched_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    consumer: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    producer: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="RECEIVED")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_token: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
