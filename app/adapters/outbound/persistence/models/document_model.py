import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.adapters.outbound.persistence.models.timestamped_model import TimestampedModel


class DocumentModel(TimestampedModel):
    __tablename__ = "documents"
    __table_args__ = (
        Index("uq_documents_sha256", "sha256", unique=True),
        Index("ix_documents_cluster_id", "cluster_id"),
        Index(
            "uq_documents_one_latest_per_cluster",
            "cluster_id",
            unique=True,
            postgresql_where=text("is_latest"),
        ),
        Index("uq_documents_cluster_version", "cluster_id", "version", unique=True),
        Index(
            "ix_documents_avg_embedding_hnsw",
            "avg_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"avg_embedding": "vector_cosine_ops"},
        ),
        CheckConstraint(
            "minhash_sig IS NULL OR cardinality(minhash_sig) = 128",
            name="ck_documents_minhash_length",
        ),
        CheckConstraint("version >= 1", name="ck_documents_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    structure_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50))
    mime_type: Mapped[str] = mapped_column(String())
    doc_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Versioning (docs/tasks/deduplication.md): all versions of one document share cluster_id.
    cluster_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    # Near-duplicate fingerprints; 768 = qwen3-embedding:0.6b, the only supported size for now.
    avg_embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    minhash_sig: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger), nullable=True)
