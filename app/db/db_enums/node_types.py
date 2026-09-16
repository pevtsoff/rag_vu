from enum import StrEnum


class NodeTypes(StrEnum):
    PREAMBLE = "preamble"
    SECTION = "section"
    ARTICLE = "article"
    ARTICLE_PART = "article_part"
    HEADER = "header"
    FOOTER = "footer"
