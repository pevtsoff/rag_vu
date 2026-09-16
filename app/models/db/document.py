import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.model_base import TimeBase

if TYPE_CHECKING:
    from app.models.db.node import Node
    from app.models.db.pipeline import Pipeline


class Document(TimeBase):
    __tablename__ = "documents"
    __table_args__ = (Index("uq_documents_sha256", "sha256", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50))
    mime_type: Mapped[str] = mapped_column(String())
    doc_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    nodes: Mapped[list["Node"]] = relationship(back_populates="document")
    pipelines: Mapped[list["Pipeline"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
