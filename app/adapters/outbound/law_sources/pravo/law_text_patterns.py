"""Recognition of legal headings and numbered article parts."""

import re

SECTION_RE = re.compile(r"^\s*РАЗДЕЛ\s+([IVXLCDM]+|\d+)\s*[\.\-:]?\s*(.*?)\s*$", re.IGNORECASE)
ARTICLE_RE = re.compile(r"^\s*СТАТЬЯ\s+(\d+(?:\.\d+)?)\s*[\.\-:]?\s*(.*?)\s*$", re.IGNORECASE)
PART_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")
PREAMBLE_RE = re.compile(r"^\s*(?:РОССИЙСКАЯ\s+ФЕДЕРАЦИЯ|ФЕДЕРАЛЬНЫЙ\s+ЗАКОН)", re.IGNORECASE)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_section_heading(line: str) -> tuple[str, str] | None:
    """Return ``(number, name)`` for ``РАЗДЕЛ I. Name``."""
    return _number_and_text(SECTION_RE, line)


def parse_article_heading(line: str) -> tuple[str, str] | None:
    """Return ``(number, name)`` for ``Статья 1. Name``."""
    return _number_and_text(ARTICLE_RE, line)


def parse_article_part(line: str) -> tuple[str, str] | None:
    """Return ``(number, text)`` for ``1. Text``."""
    return _number_and_text(PART_RE, line)


def is_preamble_heading(line: str) -> bool:
    return bool(PREAMBLE_RE.match(line))


def _number_and_text(pattern: re.Pattern[str], line: str) -> tuple[str, str] | None:
    match = pattern.match(clean_text(line))
    if not match:
        return None
    return match.group(1), clean_text(match.group(2))
