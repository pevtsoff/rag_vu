from dataclasses import dataclass, field

from app.adapters.outbound.parsing.docling.section_entry import SectionEntry
from app.domain.documents.parsed_node import ParsedNode


@dataclass
class DoclingTreeState:
    """Mutable state of one walk over a Docling document."""

    title: str
    nodes: list[ParsedNode] = field(default_factory=list)
    sections: dict[str, SectionEntry] = field(default_factory=dict)
    heading_stack: list[SectionEntry] = field(default_factory=list)
    sibling_counts: dict[str, int] = field(default_factory=dict)
    preambles: dict[int | None, list[str]] = field(default_factory=dict)
