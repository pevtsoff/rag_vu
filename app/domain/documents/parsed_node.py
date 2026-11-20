"""A node produced by a parser, before it is stored."""

from dataclasses import dataclass


@dataclass
class ParsedNode:
    title: str
    text: str
    breadcrumbs: list[str]
    path: str
    node_type: str
