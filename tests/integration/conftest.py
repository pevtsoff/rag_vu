"""Integration tests run against a real PostgreSQL with pgvector, ltree and pg_textsearch.

Set TEST_DATABASE_URL (asyncpg URL). The database is created if needed, migrated with
Alembic once per session, and emptied before every test.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine

from alembic import command
from app.bootstrap.infrastructure import Infrastructure
from app.config.app_settings import AppSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLES = "inbox_events, outbox_events, chunks, nodes, pipelines, documents"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL is not set")
    for item in items:
        if "tests/integration" in str(item.path):
            item.add_marker(skip)


def sync_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql+psycopg2").render_as_string(hide_password=False)


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


def _create_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    assert TEST_DATABASE_URL
    url = sync_url(TEST_DATABASE_URL)
    _create_database(url)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    os.environ["ALEMBIC_DATABASE_URL"] = url
    command.upgrade(alembic_config(), "head")
    yield TEST_DATABASE_URL


@pytest.fixture
def sync_engine(migrated_database: str) -> Iterator[Engine]:
    engine = create_engine(sync_url(migrated_database))
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
async def infrastructure(
    migrated_database: str, sync_engine: Engine, tmp_path: Path
) -> AsyncIterator[Infrastructure]:
    settings = AppSettings(
        database_url=migrated_database,
        upload_path=str(tmp_path / "documents"),
        embedding_provider="ollama",
    )
    infrastructure = Infrastructure(settings, null_pool=True)
    yield infrastructure
    await infrastructure.dispose()
