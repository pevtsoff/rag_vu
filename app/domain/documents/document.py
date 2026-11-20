"""The uploaded source document aggregate."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.documents.pipeline_status import PipelineStatus


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
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def start_processing(self) -> None:
        self.status = PipelineStatus.IN_PROGRESS

    def succeed(self) -> None:
        self.status = PipelineStatus.SUCCEEDED

    def fail(self) -> None:
        self.status = PipelineStatus.FAILED

    def relocate(self, file_path: str) -> None:
        """Point the document at its permanent storage location."""
        self.file_path = file_path
