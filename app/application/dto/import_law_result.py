from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ImportLawResult:
    document_id: UUID
    pipeline_id: UUID | None
    node_count: int
    duplicate: bool
