"""LawSource for pravo.gov.ru-style law pages."""

import asyncio
import re
from collections.abc import Callable

from app.adapters.outbound.law_sources.pravo.law_html_fetcher import fetch_law_html
from app.adapters.outbound.law_sources.pravo.law_node_factory import LawNodeFactory
from app.adapters.outbound.law_sources.pravo.law_page_reader import LawPageReader
from app.adapters.outbound.law_sources.pravo.law_structure_parser import LawStructureParser
from app.adapters.outbound.law_sources.pravo.law_text_splitter import (
    article_references,
    split_into_blocks,
)
from app.application.dto.law_document import LawDocument
from app.application.errors import LawImportError
from app.application.ports.law_source import LawSource


class PravoLawSource(LawSource):
    def __init__(self, fetch_html: Callable[[str], str] = fetch_law_html) -> None:
        self._fetch_html = fetch_html

    async def fetch(self, url: str) -> LawDocument:
        return await asyncio.to_thread(self.read, normalize_url(url))

    def read(self, url: str) -> LawDocument:
        reader = LawPageReader(self._fetch_html(url), url)
        title = reader.title()
        body = reader.body_text()
        nodes = LawStructureParser(LawNodeFactory(title)).parse(split_into_blocks(body))
        if not nodes:
            raise LawImportError(f"No legal text found at {url}")
        return LawDocument(
            url=url,
            title=title,
            body_text=body,
            nodes=nodes,
            metadata=reader.metadata(),
            articles=article_references(body),
        )


def normalize_url(url: str) -> str:
    """Remove whitespace that creeps into URLs copied from documents."""
    return re.sub(r"\s+", "", url)
