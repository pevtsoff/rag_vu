from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_autocommit_session
from app.models.db.document import Document
from app.models.api.document import DocumentCreate, DocumentResponse, SearchRequest, SearchResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_autocommit_session)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/search", response_model=list[SearchResponse])
async def search_documents(req: SearchRequest, db: AsyncSession = Depends(get_autocommit_session)):
    return []
