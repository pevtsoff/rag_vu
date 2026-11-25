from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.outbound.law_sources.pravo.pravo_law_source import PravoLawSource
from app.application.use_cases.documents.import_law import ImportLaw
from app.bootstrap.infrastructure import Infrastructure
from tests.integration.pipeline_runner import PipelineRunner
from tests.unit.adapters.test_pravo_law_source import DOCUMENT_HTML


async def test_an_imported_law_is_chunked_by_parts_and_embedded(
    infrastructure: Infrastructure, sync_engine: Engine
) -> None:
    source = PravoLawSource(lambda url: DOCUMENT_HTML)
    result = await ImportLaw(infrastructure.unit_of_work, source).execute(
        "https://example.test/law"
    )
    runner = PipelineRunner(infrastructure)

    assert await runner.drain() == ["chunking", "embedding", "versioning"]

    with sync_engine.connect() as connection:
        status = connection.execute(text("SELECT status FROM pipelines")).scalar()
        chunked_paths = set(
            connection.execute(
                text("SELECT n.path::text FROM chunks c JOIN nodes n ON n.id = c.node_id")
            ).scalars()
        )
    assert status == "SUCCEEDED" and result.node_count > 0
    assert {"sI.a1.p1", "sI.a1.p2", "sI.a2"} <= chunked_paths
    assert "sI.a1" not in chunked_paths  # the article is represented by its parts
