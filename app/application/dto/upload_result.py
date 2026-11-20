from dataclasses import dataclass

from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline


@dataclass(frozen=True)
class UploadResult:
    document: Document
    pipeline: Pipeline
    duplicate: bool
