import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import LtreeType

from app.adapters.outbound.persistence.models.timestamped_model import TimestampedModel

BM25_INDEX_NAME = "idx_nodes_text_bm25"


class NodeModel(TimestampedModel):
    __tablename__ = "nodes"
    __table_args__ = (
        Index(
            BM25_INDEX_NAME,
            "text",
            postgresql_using="bm25",
            postgresql_with={"text_config": "simple"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    breadcrumbs: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[object | None] = mapped_column(LtreeType(), nullable=True)
    node_type: Mapped[str] = mapped_column(String(50))
