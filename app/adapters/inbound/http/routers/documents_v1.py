from fastapi import APIRouter, Depends, File, UploadFile

from app.adapters.inbound.http.api_services import ApiServices
from app.adapters.inbound.http.dependencies import document_id_from_path, get_services
from app.adapters.inbound.http.routers.document_routes import read_document, search
from app.adapters.inbound.http.schemas.document_response import DocumentResponse
from app.adapters.inbound.http.schemas.pipeline_response import PipelineResponse
from app.adapters.inbound.http.schemas.rerun_pipeline_response import RerunPipelineResponse
from app.adapters.inbound.http.schemas.search_request import SearchRequest
from app.adapters.inbound.http.schemas.search_response import SearchResponse
from app.adapters.inbound.http.schemas.upload_document_response import UploadDocumentResponse
from app.domain.documents.pipeline_stage import PipelineStage

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    force_run: bool = False,
    services: ApiServices = Depends(get_services),
) -> UploadDocumentResponse:
    """Store the file and emit FileReceivedEvent; an identical file reuses its document."""
    result = await services.upload_document.execute(
        file, file.filename or "", file.content_type or "", force_run=force_run
    )
    return UploadDocumentResponse(
        id=str(result.document.id),
        pipeline_id=str(result.pipeline.id),
        filename=result.document.file_name,
        status=result.document.status,
        duplicate=result.duplicate,
    )


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
