"""Versioning pipeline stage; version indexes ignore soft-deleted documents.

Revision ID: 20261125_0001
Revises: 20261124_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0001"
down_revision: str | None = "20261124_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIVE = "deleted_at IS NULL"


def upgrade() -> None:
    op.add_column(
        "pipelines", sa.Column("versioned", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("pipelines", sa.Column("versioned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_pipelines_versioned"), "pipelines", ["versioned"])
    # force_upload=replace_latest soft-deletes the replaced row and gives its version number to
    # the replacement, so soft-deleted rows must not take part in the version uniqueness.
    _recreate_version_indexes(f"is_latest AND {LIVE}", LIVE)
    op.create_index(
        "ix_documents_latest_file_name",
        "documents",
        ["file_name"],
        postgresql_where=sa.text(f"is_latest AND {LIVE}"),
    )


def downgrade() -> None:
    op.drop_index("ix_documents_latest_file_name", table_name="documents")
    _recreate_version_indexes("is_latest", None)
    op.drop_index(op.f("ix_pipelines_versioned"), table_name="pipelines")
    op.drop_column("pipelines", "versioned_at")
    op.drop_column("pipelines", "versioned")


def _recreate_version_indexes(latest_where: str, version_where: str | None) -> None:
    op.drop_index("uq_documents_one_latest_per_cluster", table_name="documents")
    op.drop_index("uq_documents_cluster_version", table_name="documents")
    op.create_index(
        "uq_documents_one_latest_per_cluster",
        "documents",
        ["cluster_id"],
        unique=True,
        postgresql_where=sa.text(latest_where),
    )
    op.create_index(
        "uq_documents_cluster_version",
        "documents",
        ["cluster_id", "version"],
        unique=True,
        postgresql_where=sa.text(version_where) if version_where else None,
    )
