from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.adapters.inbound.http.api_services import ApiServices
from app.adapters.inbound.http.dependencies import document_id_from_path, get_services
from app.adapters.inbound.http.routers.document_routes import read_document, search
from app.adapters.inbound.http.schemas.document_response import DocumentResponse
from app.adapters.inbound.http.schemas.pipeline_response import PipelineResponse
from app.adapters.inbound.http.schemas.rerun_pipeline_response import RerunPipelineResponse
from app.adapters.inbound.http.schemas.search_request import SearchRequest
from app.adapters.inbound.http.schemas.search_response import SearchResponse
from app.adapters.inbound.http.schemas.upload_document_response import UploadDocumentResponse
from app.adapters.inbound.http.schemas.versioning_request import VersioningRequest
from app.application.dto.upload_override import UploadOverride
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.versioning_override import VersioningOverride

FORCE_UPLOAD_HELP = (
    "Override the automatic version assignment for a file name that already exists: "
    "replace_latest replaces that document's latest version (the old one is soft-deleted); "
    "create_new makes the upload a separate document. Unrelated to force_run, which re-runs "
    "the pipeline of an identical file."
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    force_run: bool = False,
    force_upload: VersioningOverride | None = Query(None, description=FORCE_UPLOAD_HELP),
    cluster_id: UUID | None = Query(
        None, description="Picks the target when several documents share the file name."
    ),
    services: ApiServices = Depends(get_services),
) -> UploadDocumentResponse:
    """Store the file and emit FileReceivedEvent; an identical file reuses its document."""
    result = await services.upload_document.execute(
        file,
        file.filename or "",
        file.content_type or "",
        force_run=force_run,
        override=UploadOverride(force_upload, cluster_id),
    )
    document = result.document
    return UploadDocumentResponse(
        id=str(document.id),
        pipeline_id=str(result.pipeline.id),
        filename=document.file_name,
        status=document.status,
        duplicate=result.duplicate,
        cluster_id=str(document.cluster_id),
        version=document.version,
        is_latest=document.is_latest,
    )


@router.post("/{doc_id}/versioning", response_model=DocumentResponse)
async def change_document_versioning(
    doc_id: str, request: VersioningRequest, services: ApiServices = Depends(get_services)
) -> DocumentResponse:
    """Fix a versioning decision: split the document out, or join it to another cluster."""
    document = await services.change_document_versioning.execute(
        document_id_from_path(doc_id), request.mode, request.cluster_id
    )
    return DocumentResponse.model_validate(document)


@router.get("/{doc_id}/rerun/{stage}", response_model=RerunPipelineResponse)
async def rerun_document_stage(
    doc_id: str,
    stage: PipelineStage,
    force_run: bool = False,
    services: ApiServices = Depends(get_services),
) -> RerunPipelineResponse:
    """With force_run, cancel the active run and restart from ``stage``."""
    pipeline = await services.rerun_pipeline.execute(
        document_id_from_path(doc_id), stage, force_run=force_run
    )
    return RerunPipelineResponse(
        document_id=str(pipeline.document_id), pipeline_id=str(pipeline.id), status=pipeline.status
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str, services: ApiServices = Depends(get_services)
) -> DocumentResponse:
    return await read_document(doc_id, services)


@router.get("/{doc_id}/pipelines", response_model=list[PipelineResponse])
async def get_document_pipelines(
    doc_id: str, services: ApiServices = Depends(get_services)
) -> list[PipelineResponse]:
    pipelines = await services.list_document_pipelines.execute(document_id_from_path(doc_id))
    return [PipelineResponse.model_validate(pipeline) for pipeline in pipelines]


@router.post("/search", response_model=list[SearchResponse])
async def search_documents(
    request: SearchRequest, services: ApiServices = Depends(get_services)
) -> list[SearchResponse]:
    return await search(request, services)
