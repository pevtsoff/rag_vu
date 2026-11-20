"""Splitting of law body text into heading blocks and article parts."""

from app.adapters.outbound.law_sources.pravo.law_text_patterns import (
    PART_RE,
    clean_text,
    is_preamble_heading,
    parse_article_heading,
    parse_article_part,
    parse_section_heading,
)
from app.domain.documents.node_type import NodeType

MIN_BLOCK_LENGTH = 10
MAX_ARTICLE_NAME_LENGTH = 300


def split_into_blocks(text: str) -> list[str]:
    """Split only at section and article headings; parts are split later."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if _is_heading(line.strip())]
    if not starts:
        return [text] if text.strip() else []
    if starts[0] > 0 and "\n".join(lines[: starts[0]]).strip():
        starts.insert(0, 0)
    ends = [*starts[1:], len(lines)]
    blocks = ("\n".join(lines[start:end]).strip() for start, end in zip(starts, ends, strict=True))
    return [block for block in blocks if len(block) > MIN_BLOCK_LENGTH]


def block_node_type(block: str) -> str:
    first_line = _first_line(block)
    if is_preamble_heading(first_line):
        return NodeType.PREAMBLE.value
    if parse_section_heading(first_line):
        return NodeType.SECTION.value
    if parse_article_heading(first_line):
        return NodeType.ARTICLE.value
    return NodeType.HEADER.value


def article_heading(block: str) -> tuple[str | None, str]:
    """Return the article number and name; the name may be on the following line."""
    lines = _lines(block)
    parsed = parse_article_heading(lines[0]) if lines else None
    if not parsed:
        return None, ""
    number, name = parsed
    if not name and len(lines) > 1 and _is_article_name(lines[1]):
        name = clean_text(lines[1])
    return number, name


def split_article_parts(block: str) -> list[tuple[str, str]]:
    """Return ``(number, content)`` for each numbered part; the heading is not a part."""
    lines = block.splitlines()
    starts = [index for index, line in enumerate(lines) if parse_article_part(line.strip())]
    if not starts:
        return []
    ends = [*starts[1:], len(lines)]
    parts = []
    for start, end in zip(starts, ends, strict=True):
        content = "\n".join(lines[start:end]).strip()
        parsed = parse_article_part(lines[start].strip())
        if content and parsed:
            parts.append((parsed[0], content))
    return parts


def article_references(body_text: str) -> list[dict]:
    """List distinct article headings in document order."""
    references: list[dict] = []
    seen: set[str] = set()
    for line in body_text.splitlines():
        parsed = parse_article_heading(line)
        if parsed and parsed[0] not in seen:
            seen.add(parsed[0])
            references.append({"number": parsed[0], "name": parsed[1], "type": "article"})
    return references


def _is_heading(line: str) -> bool:
    return bool(parse_section_heading(line) or parse_article_heading(line))


def _is_article_name(line: str) -> bool:
    return not _is_heading(line) and not PART_RE.match(line) and len(line) < MAX_ARTICLE_NAME_LENGTH


def _lines(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines() if line.strip()]


def _first_line(block: str) -> str:
    lines = _lines(block)
    return lines[0] if lines else ""
