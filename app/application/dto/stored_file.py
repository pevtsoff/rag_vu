from dataclasses import dataclass


@dataclass(frozen=True)
class StoredFile:
    path: str
    size: int
    sha256: str
