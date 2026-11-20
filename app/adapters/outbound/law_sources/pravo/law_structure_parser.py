"""Turns law text blocks into section, article and article-part nodes."""

from app.adapters.outbound.law_sources.pravo.law_cursor import LawCursor
from app.adapters.outbound.law_sources.pravo.law_node_factory import LawNodeFactory
from app.adapters.outbound.law_sources.pravo.law_text_patterns import parse_section_heading
from app.adapters.outbound.law_sources.pravo.law_text_splitter import (
    article_heading,
    block_node_type,
    split_article_parts,
)
from app.domain.documents.node_type import NodeType
from app.domain.documents.parsed_node import ParsedNode


class LawStructureParser:
    """Articles keep their full text and also get one child node per numbered part."""

    def __init__(self, factory: LawNodeFactory) -> None:
        self._factory = factory

    def parse(self, blocks: list[str]) -> list[ParsedNode]:
        cursor = LawCursor()
        nodes: list[ParsedNode] = []
        for block in blocks:
            node_type = block_node_type(block)
            if node_type == NodeType.SECTION.value:
                nodes.extend(self._section(block, cursor))
            elif node_type == NodeType.ARTICLE.value:
                nodes.extend(self._article(block, cursor))
            else:
                nodes.append(self._factory.other_node(block, node_type, len(nodes) + 1))
        return nodes

    def _section(self, block: str, cursor: LawCursor) -> list[ParsedNode]:
        heading = parse_section_heading(block.strip().splitlines()[0])
        if not heading:
            return []
        cursor.enter_section(*heading)
        return [self._factory.section_node(block, cursor)]

    def _article(self, block: str, cursor: LawCursor) -> list[ParsedNode]:
        number, name = article_heading(block)
        if not number:
            return []
        cursor.enter_article(number, name)
        nodes = [self._factory.article_node(block, cursor)]
        nodes.extend(
            self._factory.part_node(part_number, content, cursor)
            for part_number, content in split_article_parts(block)
        )
        return nodes
