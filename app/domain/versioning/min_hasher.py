"""128-value MinHash signatures and their Jaccard estimate.

Implemented here rather than with a library so signatures are stable across processes and
releases: they are stored in ``documents.minhash_sig`` and compared with future uploads.
"""

import hashlib
import random

from app.domain.versioning.text_normalization import words

SIGNATURE_SIZE = 128
SHINGLE_WORDS = 4
_PRIME = (1 << 61) - 1  # every value stays below 2**61, so it fits a signed BIGINT
_SEED = 20261125


class MinHasher:
    def __init__(self, size: int = SIGNATURE_SIZE, shingle_words: int = SHINGLE_WORDS) -> None:
        generator = random.Random(_SEED)
        self._coefficients = [
            (generator.randrange(1, _PRIME), generator.randrange(0, _PRIME)) for _ in range(size)
        ]
        self._shingle_words = shingle_words

    def signature(self, text: str) -> tuple[int, ...]:
        hashes = [_hash(shingle) for shingle in self._shingles(text)] or [_hash("")]
        return tuple(min((a * h + b) % _PRIME for h in hashes) for a, b in self._coefficients)

    def _shingles(self, text: str) -> set[str]:
        tokens = words(text)
        size = self._shingle_words
        if len(tokens) <= size:
            return {" ".join(tokens)} if tokens else set()
        return {" ".join(tokens[start : start + size]) for start in range(len(tokens) - size + 1)}


def lexical_similarity(
    first: tuple[int, ...] | list[int], second: tuple[int, ...] | list[int]
) -> float:
    """Share of equal positions: an estimate of the Jaccard similarity of the shingle sets."""
    if not first or len(first) != len(second):
        return 0.0
    return sum(a == b for a, b in zip(first, second, strict=True)) / len(first)


def _hash(shingle: str) -> int:
    return int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
