"""A file is stored at its permanent location and ready to be parsed."""

from dataclasses import dataclass

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class FileUploadedEvent(PipelineEvent):
    file_path: str
    file_name: str
    size: int
    sha256: str
    mime_type: str
