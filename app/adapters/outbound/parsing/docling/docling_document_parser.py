"""DocumentParser backed by Docling."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from docling_core.types.doc import ImageRefMode

from app.adapters.outbound.parsing.docling.docling_image_extractor import DoclingImageExtractor
from app.adapters.outbound.parsing.docling.docling_node_builder import DoclingNodeBuilder
from app.application.dto.parsed_document import ParsedDocument
from app.application.ports.document_parser import DocumentParser

STRUCTURE_SUFFIX = ".docling.json"


class DoclingDocumentParser(DocumentParser):
    """Converts the file, saves Docling's JSON for chunking, and builds nodes.

    Outputs are written next to the source and overwritten, so a retried job is safe.
    """

    def __init__(
        self,
        converter_factory: Callable[[], Any],
        node_builder: DoclingNodeBuilder,
        image_extractor: DoclingImageExtractor,
    ) -> None:
        self._converter_factory = converter_factory
        self._node_builder = node_builder
        self._image_extractor = image_extractor

    async def parse(self, file_path: str, fallback_title: str) -> ParsedDocument:
        return await asyncio.to_thread(self._parse, Path(file_path), fallback_title)

    def _parse(self, source: Path, fallback_title: str) -> ParsedDocument:
        if not source.is_file():
            raise FileNotFoundError(f"Uploaded file does not exist: {source}")
        document = self._converter_factory().convert(str(source)).document
        title = getattr(document, "name", None) or source.stem or fallback_title
        structure_path = f"{source}{STRUCTURE_SUFFIX}"
        document.save_as_json(structure_path, image_mode=ImageRefMode.PLACEHOLDER)
        nodes = self._node_builder.build(document, title)
        nodes.extend(self._image_extractor.extract(document, source.parent, title))
        return ParsedDocument(title=title, nodes=nodes, structure_path=structure_path)
