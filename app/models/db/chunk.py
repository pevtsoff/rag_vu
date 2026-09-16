import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.model_base import TimeBase


class Chunk(TimeBase):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("nodes.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)

    text: Mapped[str] = mapped_column(Text)
    embedding_big: Mapped[list[float] | None] = mapped_column(Vector(2048), nullable=True)
    # These are optional because some embedding providers only support one
    # configured dimension (OpenRouter's current model returns 2048).
    embedding_mid: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding_small: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    __table_args__ = (
        UniqueConstraint("node_id", "position", name="uc_node_position"),
        Index("idx_node_id", "node_id"),
    )
