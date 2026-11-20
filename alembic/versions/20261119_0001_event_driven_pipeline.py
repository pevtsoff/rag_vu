"""Event-driven pipeline: outbox/inbox tables, embedding stage, document structure path.

Revision ID: 20261119_0001
Revises: 20261101_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261119_0001"
down_revision: str | None = "20261101_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_TIMESTAMPS = ("uploaded", "parsed", "chunked")


def upgrade() -> None:
    _create_outbox_table()
    _create_inbox_table()
    _upgrade_pipelines()
    op.add_column("documents", sa.Column("structure_path", sa.String(length=1024), nullable=True))
    op.execute(
        "UPDATE documents SET structure_path = file_path || '.docling.json' "
        "WHERE file_path NOT LIKE 'http%'"
    )


def downgrade() -> None:
    op.drop_column("documents", "structure_path")
    _downgrade_pipelines()
    op.drop_index("ix_inbox_events_status_dispatched_at", table_name="inbox_events")
    op.drop_table("inbox_events")
    op.drop_index(op.f("ix_outbox_events_aggregate_id"), table_name="outbox_events")
    op.drop_index("ix_outbox_events_pending", table_name="outbox_events")
    op.drop_table("outbox_events")


def _create_outbox_table() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        *_event_columns(),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["occurred_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(op.f("ix_outbox_events_aggregate_id"), "outbox_events", ["aggregate_id"])


def _create_inbox_table() -> None:
    op.create_table(
        "inbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("consumer", sa.String(length=100), nullable=False),
        *_event_columns(),
        sa.Column("status", sa.String(length=20), server_default="RECEIVED", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_token", sa.Uuid(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "consumer", name="uq_inbox_events_event_consumer"),
    )
    op.create_index(
        "ix_inbox_events_status_dispatched_at", "inbox_events", ["status", "dispatched_at"]
    )


def _event_columns() -> list[sa.Column]:
    return [
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("producer", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    ]


def _upgrade_pipelines() -> None:
    op.add_column(
        "pipelines", sa.Column("embedded", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("pipelines", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_pipelines_embedded"), "pipelines", ["embedded"])
    for name in _LEGACY_TIMESTAMPS:
        op.execute(f"UPDATE pipelines SET {name}_at = COALESCE({name}_at, last_{name})")
        op.drop_column("pipelines", f"last_{name}")
    # The old chunking step also embedded, so chunked runs are embedded runs.
    op.execute("UPDATE pipelines SET embedded = chunked, embedded_at = chunked_at")


def _downgrade_pipelines() -> None:
    for name in _LEGACY_TIMESTAMPS:
        op.add_column(
            "pipelines", sa.Column(f"last_{name}", sa.DateTime(timezone=True), nullable=True)
        )
        op.execute(f"UPDATE pipelines SET last_{name} = {name}_at")
    op.execute("UPDATE pipelines SET stage = 'chunking' WHERE stage = 'embedding'")
    op.drop_index(op.f("ix_pipelines_embedded"), table_name="pipelines")
    op.drop_column("pipelines", "embedded_at")
    op.drop_column("pipelines", "embedded")
