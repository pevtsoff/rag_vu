"""Document versioning and near-duplicate fingerprints (docs/tasks/deduplication.md).

Revision ID: 20261124_0001
Revises: 20261119_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261124_0001"
down_revision: str | None = "20261119_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept in step with ChunkModel.content_hash. md5 is used because it is IMMUTABLE on text;
# sha256() would need convert_to(), which is only STABLE and not allowed in a generated column.
CONTENT_HASH_SQL = "md5(lower(btrim(regexp_replace(normalize(text, NFKC), '\\s+', ' ', 'g'))))"
FINGERPRINT_DIMENSIONS = 768  # qwen3-embedding:0.6b, same as chunks.embedding_small


def upgrade() -> None:
    _add_document_columns()
    _add_document_indexes()
    op.add_column(
        "chunks",
        sa.Column(
            "content_hash",
            sa.String(length=32),
            sa.Computed(CONTENT_HASH_SQL, persisted=True),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "content_hash")
    op.drop_index("ix_documents_avg_embedding_hnsw", table_name="documents")
    op.drop_index("uq_documents_cluster_version", table_name="documents")
    op.drop_index("uq_documents_one_latest_per_cluster", table_name="documents")
    op.drop_index("ix_documents_cluster_id", table_name="documents")
    for name in ("ck_documents_minhash_length", "ck_documents_version_positive"):
        op.drop_constraint(name, "documents", type_="check")
    for name in ("minhash_sig", "avg_embedding", "is_latest", "cluster_id"):
        op.drop_column("documents", name)


def _add_document_columns() -> None:
    op.add_column("documents", sa.Column("cluster_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE documents SET cluster_id = id")
    op.alter_column("documents", "cluster_id", nullable=False)
    op.add_column(
        "documents",
        sa.Column("is_latest", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("avg_embedding", Vector(FINGERPRINT_DIMENSIONS), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("minhash_sig", postgresql.ARRAY(sa.BigInteger()), nullable=True),
    )
    op.create_check_constraint(
        "ck_documents_minhash_length",
        "documents",
        "minhash_sig IS NULL OR cardinality(minhash_sig) = 128",
    )
    op.create_check_constraint("ck_documents_version_positive", "documents", "version >= 1")


def _add_document_indexes() -> None:
    op.create_index("ix_documents_cluster_id", "documents", ["cluster_id"])
    # Enforces "exactly one latest version per cluster" and serves the is_latest filter.
    op.create_index(
        "uq_documents_one_latest_per_cluster",
        "documents",
        ["cluster_id"],
        unique=True,
        postgresql_where=sa.text("is_latest"),
    )
    op.create_index(
        "uq_documents_cluster_version", "documents", ["cluster_id", "version"], unique=True
    )
    op.create_index(
        "ix_documents_avg_embedding_hnsw",
        "documents",
        ["avg_embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"avg_embedding": "vector_cosine_ops"},
    )
