from dataclasses import dataclass

from app.domain.documents.parsed_node import ParsedNode


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    nodes: list[ParsedNode]
    structure_path: str | None
