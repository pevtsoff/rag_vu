from dataclasses import dataclass


@dataclass(frozen=True)
class StagedFile:
    path: str
    file_name: str
    mime_type: str
    size: int
    sha256: str
