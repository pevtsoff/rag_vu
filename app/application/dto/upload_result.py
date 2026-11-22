from dataclasses import dataclass

from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline


@dataclass(frozen=True)
class UploadResult:
    document: Document
    pipeline: Pipeline
    duplicate: bool
    # The in-progress run that a forced re-upload cancelled, if any.
    replaced: Pipeline | None = None
