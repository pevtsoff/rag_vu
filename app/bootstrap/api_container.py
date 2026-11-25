"""Use cases exposed by the HTTP API."""

from functools import cached_property

from app.adapters.outbound.rendering.jinja_node_renderer import JinjaNodeRenderer
from app.adapters.outbound.storage.local_file_storage import LocalFileStorage
from app.application.use_cases.documents.change_document_versioning import (
    ChangeDocumentVersioning,
)
from app.application.use_cases.documents.get_document import GetDocument
from app.application.use_cases.documents.list_document_pipelines import ListDocumentPipelines
from app.application.use_cases.documents.render_node import RenderNode
from app.application.use_cases.documents.rerun_pipeline import RerunPipeline
from app.application.use_cases.documents.search_documents import SearchDocuments
from app.application.use_cases.documents.upload_document import UploadDocument
from app.bootstrap.infrastructure import Infrastructure
from app.bootstrap.query_container import QueryContainer


class ApiContainer:
    def __init__(self, infrastructure: Infrastructure) -> None:
        self.infrastructure = infrastructure
        self._uow = infrastructure.unit_of_work

    @cached_property
    def upload_document(self) -> UploadDocument:
        storage = LocalFileStorage(self.infrastructure.settings.upload_path)
        return UploadDocument(
            self._uow, storage, self.infrastructure.tracer, self.infrastructure.clock
        )

    @cached_property
    def change_document_versioning(self) -> ChangeDocumentVersioning:
        return ChangeDocumentVersioning(self._uow)

    @cached_property
    def rerun_pipeline(self) -> RerunPipeline:
        return RerunPipeline(self._uow, tracer=self.infrastructure.tracer)

    @cached_property
    def get_document(self) -> GetDocument:
        return GetDocument(self._uow)

    @cached_property
    def list_document_pipelines(self) -> ListDocumentPipelines:
        return ListDocumentPipelines(self._uow)

    @cached_property
    def render_node(self) -> RenderNode:
        return RenderNode(self._uow, JinjaNodeRenderer())

    @cached_property
    def search_documents(self) -> SearchDocuments:
        query = QueryContainer(self.infrastructure)
        return SearchDocuments(
            self.infrastructure.embedder, query.retriever, self.infrastructure.tracer
        )

    async def dispose(self) -> None:
        await self.infrastructure.dispose()
