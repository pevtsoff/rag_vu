"""What the versioning stage compares documents by."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentFingerprint:
    # None when the embedder's vectors don't have the supported size (see FINGERPRINT_DIMENSIONS).
    avg_embedding: list[float] | None
    minhash: tuple[int, ...]
    identifier: str | None = None
    redaction: str | None = None
