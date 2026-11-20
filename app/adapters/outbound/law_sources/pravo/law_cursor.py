from dataclasses import dataclass


@dataclass
class LawCursor:
    """The section and article that subsequent blocks belong to."""

    section_number: str | None = None
    section_name: str = ""
    article_number: str | None = None
    article_name: str = ""

    def enter_section(self, number: str, name: str) -> None:
        self.section_number, self.section_name = number, name
        self.article_number, self.article_name = None, ""

    def enter_article(self, number: str, name: str) -> None:
        self.article_number, self.article_name = number, name
