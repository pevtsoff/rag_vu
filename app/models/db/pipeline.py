import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.model_base import TimeBase

if TYPE_CHECKING:
    from app.models.db.document import Document


class PipelineStages(enum.StrEnum):
    PARSING = "parsing"
    CHUNKING = "chunking"
    UPLOADING = "uploading"


class PipelineStatus(enum.StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Preserve the spelling used in the initial API proposal for import compatibility.
PipielineStatus = PipelineStatus


class Pipeline(TimeBase):
    """One ingestion attempt for a document, including reruns."""

    __tablename__ = "pipelines"
    __table_args__ = (
        Index(
            "uq_pipelines_one_in_progress_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'IN_PROGRESS'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document: Mapped["Document"] = relationship(back_populates="pipelines")
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # Retain the original per-stage completion fields for existing callers.
    uploaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    last_uploaded: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parsed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    last_parsed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    last_chunked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
