"""The use cases the HTTP adapter depends on (satisfied by ApiContainer or test fakes)."""

from typing import Protocol

from app.application.use_cases.documents.change_document_versioning import (
    ChangeDocumentVersioning,
)
from app.application.use_cases.documents.get_document import GetDocument
from app.application.use_cases.documents.list_document_pipelines import ListDocumentPipelines
from app.application.use_cases.documents.render_node import RenderNode
from app.application.use_cases.documents.rerun_pipeline import RerunPipeline
from app.application.use_cases.documents.search_documents import SearchDocuments
from app.application.use_cases.documents.upload_document import UploadDocument


class ApiServices(Protocol):
    upload_document: UploadDocument
    rerun_pipeline: RerunPipeline
    get_document: GetDocument
    list_document_pipelines: ListDocumentPipelines
    render_node: RenderNode
    search_documents: SearchDocuments
    change_document_versioning: ChangeDocumentVersioning
