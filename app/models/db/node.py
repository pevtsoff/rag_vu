import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_utils import LtreeType

from app.db.db_enums.node_types import NodeTypes
from app.db.model_base import TimeBase
from app.models.db.document import Document


class Node(TimeBase):
    __tablename__ = "nodes"

    __table_args__ = (
        Index(
            "idx_nodes_text_bm25",
            "text",
            postgresql_using="bm25",
            postgresql_with={"text_config": "simple"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document: Mapped[Document] = relationship(back_populates="nodes")

    title: Mapped[str] = mapped_column(String, nullable=True)
    breadcrumbs: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=True)

    path: Mapped[str] = mapped_column(LtreeType(), nullable=True)
    node_type: Mapped[str] = mapped_column(String(50), default=NodeTypes.HEADER.value)
