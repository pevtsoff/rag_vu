"""Attribute names of the application's own span attributes (``rag.*``)."""

from app.application.ports.trace_span import TraceValue
from app.domain.documents.document import Document
from app.domain.events.pipeline_event import PipelineEvent

FILE_NAME = "rag.file.name"
FILE_SIZE = "rag.file.size_bytes"
FILE_PATH = "rag.file.path"
FILE_MIME_TYPE = "rag.file.mime_type"
FILE_SHA256 = "rag.file.sha256"
STAGED_PATH = "rag.file.staged_path"
STORED_PATH = "rag.file.stored_path"

DOCUMENT_ID = "rag.document.id"
PIPELINE_ID = "rag.pipeline.id"
PIPELINE_STAGE = "rag.pipeline.stage"
PIPELINE_STATUS = "rag.pipeline.status"
PIPELINE_ERROR_STAGE = "rag.pipeline.error_stage"
PIPELINE_STAGES_DONE = "rag.pipeline.completed_stages"
EVENT_TYPE = "rag.event.type"
EVENT_ID = "rag.event.id"
INBOX_ID = "rag.inbox.id"
INBOX_ATTEMPTS = "rag.inbox.attempts"
JOB_CONSUMER = "rag.job.consumer"
JOB_OUTCOME = "rag.job.outcome"

UPLOAD_DUPLICATE = "rag.upload.duplicate"
UPLOAD_FORCE_RUN = "rag.upload.force_run"
UPLOAD_VERIFIED = "rag.upload.verified"
UPLOAD_FORCE_UPLOAD = "rag.upload.force_upload"
UPLOAD_CLUSTER_ID = "rag.upload.cluster_id"

VERSIONING_IDENTIFIER = "rag.versioning.identifier"
VERSIONING_REDACTION = "rag.versioning.redaction"
VERSIONING_HAS_EMBEDDING = "rag.versioning.has_avg_embedding"
VERSIONING_CHUNK_COUNT = "rag.versioning.chunk_count"

PARSE_TITLE = "rag.parse.title"
PARSE_NODE_COUNT = "rag.parse.node_count"
PARSE_NODE_TYPES = "rag.parse.node_type_counts"
PARSE_TEXT_CHARS = "rag.parse.text_chars"
PARSE_STRUCTURE_PATH = "rag.parse.structure_path"

CHUNK_SOURCE_NODES = "rag.chunk.source_node_count"
CHUNK_COUNT = "rag.chunk.count"
CHUNK_AVG_CHARS = "rag.chunk.avg_chars"
CHUNK_MIN_CHARS = "rag.chunk.min_chars"
CHUNK_MAX_CHARS = "rag.chunk.max_chars"

EMBEDDING_COUNT = "rag.embedding.count"
EMBEDDING_DIMENSIONS = "rag.embedding.dimensions"
EMBEDDING_BATCH_SIZE = "rag.embedding.batch_size"
EMBEDDING_BATCH_COUNT = "rag.embedding.batch_count"
EMBEDDING_TASK = "rag.embedding.task"
EMBEDDING_TEXT_COUNT = "rag.embedding.text_count"
EMBEDDING_TEXT_CHARS = "rag.embedding.text_chars"

QUERY_HISTORY_MESSAGES = "rag.query.history_messages"
QUERY_RETRIEVAL_QUERY = "rag.query.retrieval_query"
QUERY_REWRITTEN = "rag.query.rewritten_from_history"
QUERY_SOURCE_COUNT = "rag.query.source_count"
QUERY_CONTEXT_CHARS = "rag.query.context_chars"
QUERY_REASONING_REMOVED = "rag.query.reasoning_removed"
QUERY_TOP_K = "rag.query.top_k"

RETRIEVAL_SOURCE = "rag.retrieval.source"
RETRIEVAL_CANDIDATE_COUNT = "rag.retrieval.candidate_count"
RETRIEVAL_VECTOR_DIMENSIONS = "rag.retrieval.vector_dimensions"
RETRIEVAL_LATEST_ONLY = "rag.retrieval.latest_only"
QUERY_VERSION_COUNT = "rag.query.version_count"
RERANK_ORDER_CHANGED = "rag.rerank.order_changed"
LLM_FINISH_REASON = "rag.llm.finish_reason"


def with_pipeline_id(name: str, pipeline_id: object) -> str:
    """Span name that shows its pipeline run in Phoenix's span list, e.g. ``x [<id>]``."""
    return f"{name} [{pipeline_id}]"


def document_attributes(document: Document) -> dict[str, TraceValue | None]:
    return {
        DOCUMENT_ID: str(document.id),
        FILE_NAME: document.file_name,
        FILE_SIZE: document.size,
        FILE_PATH: document.file_path,
        FILE_MIME_TYPE: document.mime_type,
        FILE_SHA256: document.sha256,
    }


def pipeline_event_attributes(event: PipelineEvent) -> dict[str, TraceValue | None]:
    return {
        DOCUMENT_ID: str(event.document_id),
        PIPELINE_ID: str(event.pipeline_id),
        EVENT_TYPE: event.event_type,
        EVENT_ID: str(event.event_id),
    }
