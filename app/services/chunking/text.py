"""Text normalization and semantic splitting helpers."""

import re

SPLIT_THRESHOLD = 500
TARGET_CHUNK_SIZE = 900
MAX_CHUNK_SIZE = 1400
PARAGRAPH_RE = re.compile(r"\n\s*\n+")
SENTENCE_RE = re.compile(r'(?<=[.!?])(?:["»”\']+)?\s+(?=[А-ЯЁA-Z0-9«"„“])')


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for paragraph in PARAGRAPH_RE.split(text):
        paragraph = re.sub(r"[ \t]+", " ", paragraph)
        paragraph = re.sub(r"\n+", " ", paragraph).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def _pack_segments(segments: list[str], separator: str, split_oversized) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for segment in segments:
        if len(segment) > MAX_CHUNK_SIZE:
            if current:
                chunks.append(separator.join(current))
                current, current_length = [], 0
            chunks.extend(split_oversized(segment))
            continue
        separator_length = len(separator) if current else 0
        if current and current_length + separator_length + len(segment) > TARGET_CHUNK_SIZE:
            chunks.append(separator.join(current))
            current, current_length = [], 0
        current.append(segment)
        current_length += (len(separator) if len(current) > 1 else 0) + len(segment)
    if current:
        chunks.append(separator.join(current))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def hard_split(text: str) -> list[str]:
    result, current, current_length = [], [], 0
    for word in text.split():
        additional_length = len(word) if not current else len(word) + 1
        if current and current_length + additional_length > TARGET_CHUNK_SIZE:
            result.append(" ".join(current))
            current, current_length = [], 0
        current.append(word)
        current_length += len(word) if len(current) == 1 else len(word) + 1
    if current:
        result.append(" ".join(current))
    return result


def split_sentences(text: str) -> list[str]:
    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(text) if sentence.strip()]
    return _pack_segments(sentences, " ", hard_split)


def split_long_part(text: str) -> list[str]:
    text = normalize_text(text)
    if len(text) <= SPLIT_THRESHOLD:
        return [text]
    paragraphs = text.split("\n\n")
    if len(paragraphs) == 1:
        return split_sentences(text)
    return _pack_segments(paragraphs, "\n\n", split_sentences)
