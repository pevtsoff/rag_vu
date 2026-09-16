"""A parsed document node ready for database persistence."""

from dataclasses import dataclass


@dataclass
class ParsedNode:
    title: str
    text: str
    breadcrumbs: list[str]
    path: str
    node_type: str
