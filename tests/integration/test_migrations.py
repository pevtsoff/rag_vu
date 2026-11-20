from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Engine

from alembic import command
from app.adapters.outbound.persistence.models import Base
from tests.integration.conftest import alembic_config


def test_migrated_schema_matches_the_orm_models(sync_engine: Engine) -> None:
    with sync_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_event_pipeline_migration_converts_existing_pipelines(sync_engine: Engine) -> None:
    config = alembic_config()
    command.downgrade(config, "20261101_0001")
    try:
        with sync_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents (id, file_name, file_path, size, status, mime_type, version) "
                    "VALUES ('00000000-0000-0000-0000-000000000001', 'a.pdf', '/m/a.pdf', 1, 'SUCCEEDED', 'application/pdf', 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO pipelines (id, document_id, stage, status, uploaded, parsed, chunked, last_chunked) "
                    "VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', "
                    "'chunking', 'SUCCEEDED', true, true, true, '2026-10-01T00:00:00Z')"
                )
            )
    finally:
        command.upgrade(config, "head")
    with sync_engine.connect() as connection:
        embedded, embedded_at, chunked_at = connection.execute(
            text("SELECT embedded, embedded_at, chunked_at FROM pipelines")
        ).one()
        structure_path = connection.execute(text("SELECT structure_path FROM documents")).scalar()
    assert embedded and embedded_at == chunked_at and chunked_at is not None
    assert structure_path == "/m/a.pdf.docling.json"


def test_required_extensions_are_installed(sync_engine: Engine) -> None:
    with sync_engine.connect() as connection:
        names = set(connection.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert {"vector", "ltree", "pg_textsearch"} <= names
