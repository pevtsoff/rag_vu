"""The uploaded source document aggregate."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.documents.pipeline_status import PipelineStatus

VERSIONING_KEY = "versioning"
DUPLICATE_OF_KEY = "duplicate_of"
IDENTIFIER_KEY = "identifier"
REDACTION_KEY = "redaction"


@dataclass(kw_only=True)
class Document:
    file_name: str
    file_path: str
    size: int
    mime_type: str
    sha256: str | None = None
    id: UUID = field(default_factory=uuid4)
    status: PipelineStatus = PipelineStatus.IN_PROGRESS
    structure_path: str | None = None
    doc_metadata: dict | None = None
    version: int = 1
    cluster_id: UUID | None = None  # defaults to id: a new document starts its own cluster
    is_latest: bool = True
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.cluster_id is None:
            self.cluster_id = self.id

    def start_processing(self) -> None:
        self.status = PipelineStatus.IN_PROGRESS

    def succeed(self) -> None:
        self.status = PipelineStatus.SUCCEEDED

    def fail(self) -> None:
        self.status = PipelineStatus.FAILED

    def relocate(self, file_path: str) -> None:
        """Point the document at its permanent storage location."""
        self.file_path = file_path

    @property
    def is_alone_in_own_cluster(self) -> bool:
        """True until versioning has attached this document to another document."""
        return self.cluster_id == self.id and self.version == 1

    @property
    def is_duplicate(self) -> bool:
        return bool((self.doc_metadata or {}).get(DUPLICATE_OF_KEY))

    @property
    def versioning(self) -> dict[str, Any]:
        return dict((self.doc_metadata or {}).get(VERSIONING_KEY) or {})

    def supersede(self) -> None:
        """A newer version of this document became the latest one."""
        self.is_latest = False

    def join_cluster(self, cluster_id: UUID, version: int) -> None:
        """Become ``version`` of ``cluster_id``, as its latest version."""
        self.cluster_id = cluster_id
        self.version = version
        self.is_latest = True

    def start_own_cluster(self) -> None:
        """Leave any cluster and become version 1 of a new one."""
        self.join_cluster(self.id, 1)

    def soft_delete(self, at: datetime) -> None:
        """Hide the document (and its chunks) from retrieval without losing its history."""
        self.deleted_at = at
        self.is_latest = False

    def clear_duplicate(self) -> None:
        self.doc_metadata = {
            key: value
            for key, value in (self.doc_metadata or {}).items()
            if key != DUPLICATE_OF_KEY
        }

    def mark_duplicate_of(self, original_id: UUID) -> None:
        self.is_latest = False
        self.set_metadata(DUPLICATE_OF_KEY, str(original_id))

    def record_versioning(self, decision: dict[str, Any]) -> None:
        """Keep why the document has its cluster and version, for people and traces."""
        self.set_metadata(VERSIONING_KEY, decision)

    def set_metadata(self, key: str, value: Any) -> None:
        self.doc_metadata = {**(self.doc_metadata or {}), key: value}
