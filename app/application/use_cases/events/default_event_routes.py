"""The ingestion pipeline: each stage job listens to its predecessor's event."""

from app.application.dto.job_route import JobRoute
from app.application.use_cases.events.event_routes import EventRoutes
from app.domain.events.document_chunked_event import DocumentChunkedEvent
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.file_received_event import FileReceivedEvent
from app.domain.events.file_uploaded_event import FileUploadedEvent

UPLOAD_ROUTE = JobRoute(consumer="upload", queue="upload")
PARSING_ROUTE = JobRoute(consumer="parsing", queue="parsing")
CHUNKING_ROUTE = JobRoute(consumer="chunking", queue="chunking")
EMBEDDING_ROUTE = JobRoute(consumer="embedding", queue="embedding")


def default_event_routes() -> EventRoutes:
    return EventRoutes(
        {
            FileReceivedEvent.event_type: (UPLOAD_ROUTE,),
            FileUploadedEvent.event_type: (PARSING_ROUTE,),
            DocumentParsedEvent.event_type: (CHUNKING_ROUTE,),
            DocumentChunkedEvent.event_type: (EMBEDDING_ROUTE,),
        }
    )
