"""Which document version a retrieved passage comes from."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class MatchVersion:
    document_id: str
    cluster_id: str
    version: int
    is_latest: bool
    file_name: str
    created_at: datetime | None
    redaction: str | None
    content_hash: str
    # Every version that has this exact passage; set when unchanged passages are collapsed.
    versions: tuple[int, ...] = field(default=())

    @property
    def covered_versions(self) -> tuple[int, ...]:
        return self.versions or (self.version,)
