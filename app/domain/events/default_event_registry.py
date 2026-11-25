"""The registry of every event the application produces."""

from app.domain.events.document_chunked_event import DocumentChunkedEvent
from app.domain.events.document_embedded_event import DocumentEmbeddedEvent
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.document_versioned_event import DocumentVersionedEvent
from app.domain.events.event_registry import EventRegistry
from app.domain.events.file_received_event import FileReceivedEvent
from app.domain.events.file_uploaded_event import FileUploadedEvent
from app.domain.events.pipeline_failed_event import PipelineFailedEvent


def default_event_registry() -> EventRegistry:
    return EventRegistry(
        [
            FileReceivedEvent,
            FileUploadedEvent,
            DocumentParsedEvent,
            DocumentChunkedEvent,
            DocumentEmbeddedEvent,
            DocumentVersionedEvent,
            PipelineFailedEvent,
        ]
    )
