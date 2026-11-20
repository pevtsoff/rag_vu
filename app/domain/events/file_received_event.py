"""A file was accepted by the API and staged for the upload stage."""

from dataclasses import dataclass

from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True, kw_only=True)
class FileReceivedEvent(PipelineEvent):
    staged_path: str
    file_name: str
    size: int
    sha256: str
    mime_type: str
