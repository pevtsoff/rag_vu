from dataclasses import dataclass

from app.domain.documents.parsed_node import ParsedNode


@dataclass
class SectionEntry:
    """A heading already turned into a node, remembered for its descendants."""

    title: str
    key: str
    ordinal: int
    node: ParsedNode
    level: int
