"""What a stage job loaded in its prepare step."""

from dataclasses import dataclass
from typing import Any

from app.domain.documents.document import Document
from app.domain.events.pipeline_event import PipelineEvent


@dataclass(frozen=True)
class StageContext:
    event: PipelineEvent
    document: Document
    data: Any = None
