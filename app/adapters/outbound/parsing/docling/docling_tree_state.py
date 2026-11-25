from dataclasses import dataclass, field

from app.adapters.outbound.parsing.docling.section_entry import SectionEntry
from app.domain.documents.parsed_node import ParsedNode


@dataclass(frozen=True)
class ChapterTitle:
    """A top-level chapter listed in the table of contents."""

    title: str
    key: str


@dataclass
class DoclingTreeState:
    """Mutable state of one walk over a Docling document."""

    title: str
    nodes: list[ParsedNode] = field(default_factory=list)
    sections: dict[str, SectionEntry] = field(default_factory=dict)
    heading_stack: list[SectionEntry] = field(default_factory=list)
    sibling_counts: dict[str, int] = field(default_factory=dict)
    preambles: dict[int | None, list[str]] = field(default_factory=dict)
    chapters: list[ChapterTitle] = field(default_factory=list)
    next_chapter: int = 0
    chapter: SectionEntry | None = None
    # (full chapter key, key of the headings merged so far) while a title spans headings.
    pending_chapter: tuple[str, str] | None = None
    contents_count: int = 0
