"""Paragraph- and sentence-aware splitting of long node text."""

import re
from collections.abc import Callable

SPLIT_THRESHOLD = 500
TARGET_CHUNK_SIZE = 900
MAX_CHUNK_SIZE = 1400
PARAGRAPH_RE = re.compile(r"\n\s*\n+")
SENTENCE_RE = re.compile(r'(?<=[.!?])(?:["»”\']+)?\s+(?=[А-ЯЁA-Z0-9«"„“])')


def normalize_text(text: str) -> str:
    """Collapse whitespace inside paragraphs and keep blank lines between them."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for paragraph in PARAGRAPH_RE.split(text):
        paragraph = re.sub(r"[ \t]+", " ", paragraph)
        paragraph = re.sub(r"\n+", " ", paragraph).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def split_long_part(text: str) -> list[str]:
    text = normalize_text(text)
    if len(text) <= SPLIT_THRESHOLD:
        return [text]
    paragraphs = text.split("\n\n")
    if len(paragraphs) == 1:
        return split_sentences(text)
    return _pack_segments(paragraphs, "\n\n", split_sentences)


def split_sentences(text: str) -> list[str]:
    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(text) if sentence.strip()]
    return _pack_segments(sentences, " ", hard_split)


def hard_split(text: str) -> list[str]:
    """Split at word boundaries when no sentence boundary is available."""
    result, current, current_length = [], [], 0
    for word in text.split():
        additional_length = len(word) if not current else len(word) + 1
        if current and current_length + additional_length > TARGET_CHUNK_SIZE:
            result.append(" ".join(current))
            current, current_length = [], 0
            additional_length = len(word)
        current.append(word)
        current_length += additional_length
    if current:
        result.append(" ".join(current))
    return result


def _pack_segments(
    segments: list[str], separator: str, split_oversized: Callable[[str], list[str]]
) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for segment in segments:
        if len(segment) > MAX_CHUNK_SIZE:
            chunks.extend([separator.join(current)] if current else [])
            chunks.extend(split_oversized(segment))
            current = []
            continue
        candidate_length = len(separator.join([*current, segment]))
        if current and candidate_length > TARGET_CHUNK_SIZE:
            chunks.append(separator.join(current))
            current = []
        current.append(segment)
    if current:
        chunks.append(separator.join(current))
    return [chunk.strip() for chunk in chunks if chunk.strip()]
