from dataclasses import dataclass, field

from app.domain.documents.parsed_node import ParsedNode


@dataclass(frozen=True)
class LawDocument:
    url: str
    title: str
    body_text: str
    nodes: list[ParsedNode]
    metadata: dict = field(default_factory=dict)
    articles: list[dict] = field(default_factory=list)
