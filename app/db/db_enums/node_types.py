from enum import StrEnum


class NodeTypes(StrEnum):
    PREAMBLE = "preamble"
    SECTION = "section"
    ARTICLE = "article"
    ARTICLE_SECTION = "article_section"
    ARTICLE_PART = "article_part"
    HEADER = "header"
    FOOTER = "footer"
