import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

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


_INSERT_DOCUMENT = text(
    "INSERT INTO documents (id, file_name, file_path, size, status, mime_type, version, "
    "cluster_id, is_latest, minhash_sig) VALUES (gen_random_uuid(), 'a.pdf', '/m/a.pdf', 1, "
    "'SUCCEEDED', 'application/pdf', :version, :cluster_id, :is_latest, :minhash_sig)"
)
_CLUSTER = "00000000-0000-0000-0000-0000000000c1"


def _insert_document(engine: Engine, version: int, is_latest: bool, minhash=None) -> None:
    with engine.begin() as connection:
        connection.execute(
            _INSERT_DOCUMENT,
            {
                "version": version,
                "cluster_id": _CLUSTER,
                "is_latest": is_latest,
                "minhash_sig": minhash,
            },
        )


@pytest.mark.parametrize(
    ("version", "is_latest", "minhash"),
    [
        (2, True, None),  # a second latest version in the cluster
        (1, False, None),  # a repeated version number
        (0, False, None),  # versions start at 1
        (2, False, [1, 2, 3]),  # MinHash signatures have 128 values
    ],
)
def test_document_versioning_rules_are_enforced(
    sync_engine: Engine, version: int, is_latest: bool, minhash: list[int] | None
) -> None:
    _insert_document(sync_engine, version=1, is_latest=True)
    with pytest.raises(IntegrityError):
        _insert_document(sync_engine, version=version, is_latest=is_latest, minhash=minhash)


def test_chunk_content_hash_ignores_case_and_whitespace(sync_engine: Engine) -> None:
    _insert_document(sync_engine, version=1, is_latest=True)
    with sync_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO nodes (id, document_id, node_type) "
                "SELECT gen_random_uuid(), id, 'article' FROM documents"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chunks (id, node_id, position, text) "
                "SELECT gen_random_uuid(), nodes.id, p, t FROM nodes, (VALUES "
                "(0, E'Статья 18.\\n  Права'), (1, 'статья 18. права '), (2, 'Статья 19.')) "
                "AS v(p, t)"
            )
        )
        hashes = (
            connection.execute(text("SELECT content_hash FROM chunks ORDER BY position"))
            .scalars()
            .all()
        )
    assert hashes[0] == hashes[1] != hashes[2]
