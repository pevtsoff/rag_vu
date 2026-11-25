"""Docling chunking serializers that render tables with the same text the nodes store."""

from typing import Any, override

from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.serializer.base import (
    BaseDocSerializer,
    BaseTableSerializer,
    SerializationResult,
)
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.types.doc import DoclingDocument

from app.adapters.outbound.parsing.docling.docling_tables import table_to_text

HEADER_LINE_COUNT = 2  # a Markdown header row and its separator


class TableTextSerializer(BaseTableSerializer):
    """Replaces Docling's ``row, column = value`` triplets with ``table_to_text``."""

    @override
    def serialize(
        self,
        *,
        item: Any,
        doc_serializer: BaseDocSerializer,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        return create_ser_result(text=table_to_text(item), span_source=item)

    @override
    def get_header_and_body_lines(
        self, *, table_text: str, **kwargs: Any
    ) -> tuple[list[str], list[str]]:
        """A split table repeats its header row and separator in every chunk."""
        lines = [line for line in table_text.split("\n") if line.strip()]
        if len(lines) > 1 and set(lines[1].replace("|", "").split()) == {"---"}:
            return lines[:HEADER_LINE_COUNT], lines[HEADER_LINE_COUNT:]
        return [], lines


class TableTextSerializerProvider(ChunkingSerializerProvider):
    @override
    def get_serializer(self, doc: DoclingDocument) -> BaseDocSerializer:
        return ChunkingDocSerializer(doc=doc, table_serializer=TableTextSerializer())
