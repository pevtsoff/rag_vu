"""Keep at most one active pipeline per document."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261101_0001"
down_revision: Union[str, None] = "dab90acfb006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY document_id ORDER BY created_at DESC, id DESC
                ) AS position
                FROM pipelines
                WHERE status = 'IN_PROGRESS'
            )
            UPDATE pipelines
            SET status = 'CANCELLED'
            FROM ranked
            WHERE pipelines.id = ranked.id AND ranked.position > 1
            """
        )
    )
    op.create_index(
        "uq_pipelines_one_in_progress_per_document",
        "pipelines",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'IN_PROGRESS'"),
    )


def downgrade() -> None:
    op.drop_index("uq_pipelines_one_in_progress_per_document", table_name="pipelines")
