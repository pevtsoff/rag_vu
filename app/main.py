from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import documents as v1_documents
from app.api.v1 import nodes as v1_nodes
from app.api.v2 import documents as v2_documents

app = FastAPI(
    title="RAG-VU API",
    description="Retrieval-Augmented Generation API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_documents.router, prefix="/api/v1")
app.include_router(v1_nodes.router, prefix="/api/v1")
app.include_router(v2_documents.router, prefix="/api/v2")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
