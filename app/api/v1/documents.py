from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_autocommit_session, get_simple_session
from app.models.api.document import (
    DocumentResponse,
    PipelineResponse,
    SearchRequest,
    SearchResponse,
)
from app.models.api.document.rerun_pipeline import RerunPipeline
from app.models.api.document.upload_document import UploadDocument
from app.models.db.pipeline import PipelineStages
from app.services.api.documents.common import (
    get_document_record,
    search_documents,
)
from app.services.api.documents.pipelines import get_document_pipelines
from app.services.api.documents.rerun_stage import rerun_pipeline_from_stage
from app.services.api.documents.upload_document import upload_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadDocument)
async def upload_document_route(
    file: UploadFile = File(...),
    force_run: bool = False,
    session: AsyncSession = Depends(get_simple_session),
):
    return await upload_document(file, session, force_run=force_run)


@router.get("/{doc_id}/rerun/{stage}", response_model=RerunPipeline)
async def rerun_document_stage_route(
    doc_id: str,
    stage: PipelineStages,
    force_run: bool = False,
    session: AsyncSession = Depends(get_simple_session),
):
    return await rerun_pipeline_from_stage(doc_id, stage, session, force_run=force_run)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_autocommit_session)):
    return await get_document_record(doc_id, db)


@router.get("/{doc_id}/pipelines", response_model=list[PipelineResponse])
async def get_document_pipelines_route(
    doc_id: str, db: AsyncSession = Depends(get_autocommit_session)
):
    return await get_document_pipelines(doc_id, db)


@router.post("/search", response_model=list[SearchResponse])
async def search_documents_route(
    req: SearchRequest, db: AsyncSession = Depends(get_autocommit_session)
):
    return await search_documents(req, db)
