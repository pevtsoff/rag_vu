"""Text normalisation shared by MinHash shingles and passage hashes."""

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_WORD = re.compile(r"\w+", re.UNICODE)


def normalize_text(text: str) -> str:
    """NFKC, lowercase, collapsed whitespace: the same rule as ``chunks.content_hash``."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip().lower()


def content_hash(text: str) -> str:
    """md5 of the normalised text; equal to the ``chunks.content_hash`` column for chunk text."""
    return hashlib.md5(normalize_text(text).encode("utf-8")).hexdigest()


def words(text: str) -> list[str]:
    return _WORD.findall(normalize_text(text))
