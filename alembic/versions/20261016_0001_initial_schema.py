"""Create the application schema, including the node BM25 index."""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261016_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_textsearch")

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("doc_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_documents_sha256", "documents", ["sha256"], unique=True)

    op.create_table(
        "nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("breadcrumbs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("path", sqlalchemy_utils.types.ltree.LtreeType(), nullable=True),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_nodes_document_id"), "nodes", ["document_id"], unique=False)
    op.create_index(
        "idx_nodes_text_bm25",
        "nodes",
        ["text"],
        unique=False,
        postgresql_using="bm25",
        postgresql_with={"text_config": "simple"},
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_big", pgvector.sqlalchemy.vector.VECTOR(dim=2048), nullable=True),
        sa.Column("embedding_mid", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
        sa.Column("embedding_small", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "position", name="uc_node_position"),
    )
    op.create_index("idx_node_id", "chunks", ["node_id"], unique=False)

    op.create_table(
        "pipelines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("uploaded", sa.Boolean(), nullable=False),
        sa.Column("last_uploaded", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed", sa.Boolean(), nullable=False),
        sa.Column("last_parsed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chunked", sa.Boolean(), nullable=False),
        sa.Column("last_chunked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chunked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_stage", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipelines_document_id"), "pipelines", ["document_id"])
    op.create_index(op.f("ix_pipelines_status"), "pipelines", ["status"])
    op.create_index(op.f("ix_pipelines_uploaded"), "pipelines", ["uploaded"])
    op.create_index(op.f("ix_pipelines_parsed"), "pipelines", ["parsed"])
    op.create_index(op.f("ix_pipelines_chunked"), "pipelines", ["chunked"])


def downgrade() -> None:
    op.drop_index(op.f("ix_pipelines_chunked"), table_name="pipelines")
    op.drop_index(op.f("ix_pipelines_parsed"), table_name="pipelines")
    op.drop_index(op.f("ix_pipelines_uploaded"), table_name="pipelines")
    op.drop_index(op.f("ix_pipelines_status"), table_name="pipelines")
    op.drop_index(op.f("ix_pipelines_document_id"), table_name="pipelines")
    op.drop_table("pipelines")
    op.drop_index("idx_node_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("idx_nodes_text_bm25", table_name="nodes")
    op.drop_index(op.f("ix_nodes_document_id"), table_name="nodes")
    op.drop_table("nodes")
    op.drop_index("uq_documents_sha256", table_name="documents")
    op.drop_table("documents")
