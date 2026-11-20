"""Import laws from pravo.gov.ru-style pages into the ingestion pipeline.

``python -m app.adapters.inbound.cli.import_law URL [URL ...] [--nodes-json DIR]``
"""

import argparse
import asyncio
import dataclasses
import json
from pathlib import Path

from app.adapters.outbound.law_sources.pravo.pravo_law_source import PravoLawSource
from app.application.dto.law_document import LawDocument
from app.application.ports.law_source import LawSource
from app.application.use_cases.documents.import_law import ImportLaw
from app.bootstrap.infrastructure import Infrastructure
from app.config.app_settings import get_settings


class _RecordingSource(LawSource):
    """Keeps fetched laws so their nodes can be written to JSON for inspection."""

    def __init__(self, inner: LawSource) -> None:
        self._inner = inner
        self.fetched: list[LawDocument] = []

    async def fetch(self, url: str) -> LawDocument:
        law = await self._inner.fetch(url)
        self.fetched.append(law)
        return law


async def main(urls: list[str], nodes_json: Path | None) -> None:
    infrastructure = Infrastructure(get_settings())
    source = _RecordingSource(PravoLawSource())
    use_case = ImportLaw(infrastructure.unit_of_work, source)
    try:
        for url in urls:
            result = await use_case.execute(url)
            state = "already imported" if result.duplicate else f"{result.node_count} nodes"
            print(f"{url}: document {result.document_id} ({state})")
    finally:
        await infrastructure.dispose()
    if nodes_json is not None:
        _write_nodes(source.fetched, nodes_json)


def _write_nodes(laws: list[LawDocument], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index, law in enumerate(laws, start=1):
        nodes = [dataclasses.asdict(node) for node in law.nodes]
        path = folder / f"law_{index}_nodes.json"
        path.write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+", help="Law page URLs")
    parser.add_argument("--nodes-json", type=Path, help="Also write parsed nodes to this folder")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    asyncio.run(main(arguments.urls, arguments.nodes_json))
