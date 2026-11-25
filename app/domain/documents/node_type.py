"""Kinds of structural nodes extracted from a document."""

from enum import StrEnum


class NodeType(StrEnum):
    PREAMBLE = "preamble"
    SECTION = "section"
    ARTICLE = "article"
    ARTICLE_SECTION = "article_section"
    ARTICLE_PART = "article_part"
    HEADER = "header"
    FOOTER = "footer"
    IMAGE = "image"
    # A table of contents: kept for readers (and for chapter structure), never searched.
    CONTENTS = "contents"

    @classmethod
    def retrievable(cls) -> frozenset["NodeType"]:
        """Node types that can be searched for and rendered as a source."""
        return frozenset(
            {
                cls.ARTICLE,
                cls.ARTICLE_SECTION,
                cls.ARTICLE_PART,
                cls.SECTION,
                cls.PREAMBLE,
                cls.HEADER,
            }
        )

    @classmethod
    def article_family(cls) -> frozenset["NodeType"]:
        """Node types that belong to a legal article hierarchy."""
        return frozenset({cls.ARTICLE, cls.ARTICLE_SECTION, cls.ARTICLE_PART})
