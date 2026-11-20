import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.adapters.outbound.persistence.models.timestamped_model import TimestampedModel


class PipelineModel(TimestampedModel):
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
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    uploaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    parsed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    chunked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    embedded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
