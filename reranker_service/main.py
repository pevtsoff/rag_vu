"""Small FastAPI microservice that serves Qwen3-Reranker-0.6B via
sentence-transformers' CrossEncoder, which has native support for this
model's causal-LM scoring scheme (sigmoid(logit("yes") - logit("no"))
at the final token) - see the model card for ``Qwen/Qwen3-Reranker-0.6B``.

Why this exists instead of Ollama or text-embeddings-inference:

* Ollama has no built-in /api/rerank endpoint; the only way to use an
  Ollama-served model for reranking is listwise LLM prompting (see
  ``app/adapters/outbound/rerank/ollama_reranker.py``), which this repo
  already supports but which underperforms a dedicated cross-encoder.
* text-embeddings-inference explicitly does not support Qwen3-Reranker's
  architecture (Qwen3ForCausalLM is not a supported "classifier" model
  type - huggingface/text-embeddings-inference#643).
* sentence-transformers' CrossEncoder has first-class support for this
  exact checkpoint and needs no custom prompt/scoring logic.

The HTTP contract intentionally mirrors OpenRouter's /v1/rerank shape
({query, documents, top_n} -> {"results": [{"index", "relevance_score"}]})
so the request/response parsing already written in this repo's rerank
adapters can be reused almost as-is for the new provider.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("reranker_service")

MODEL_NAME = os.environ.get("RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B")
MAX_LENGTH = int(os.environ.get("RERANKER_MAX_LENGTH", "512"))

# Loaded once at startup (see lifespan below) and reused across requests.
# sentence-transformers' CrossEncoder is not documented as thread-safe for
# concurrent .predict() calls, so we serialize access with a lock rather
# than risk corrupting shared model state under uvicorn's default
# multi-worker-per-process concurrency (this service is CPU-bound anyway,
# so serializing scoring batches is not a meaningful bottleneck).
_model: CrossEncoder | None = None
_model_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    logger.info("Loading reranker model %s (max_length=%d)...", MODEL_NAME, MAX_LENGTH)
    _model = CrossEncoder(MODEL_NAME, max_length=MAX_LENGTH)
    logger.info("Reranker model loaded.")
    yield
    _model = None


app = FastAPI(title="rag_vu local reranker", lifespan=lifespan)


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_n: int | None = Field(default=None, ge=1)
    model: str | None = None  # accepted for API-shape compatibility, ignored


class RerankResult(BaseModel):
    index: int
    relevance_score: float


class RerankResponse(BaseModel):
    results: list[RerankResult]


@app.get("/health")
def health() -> dict[str, str]:
    if _model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/rerank", response_model=RerankResponse)
def rerank(request: RerankRequest) -> RerankResponse:
    if _model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    if not request.documents:
        return RerankResponse(results=[])

    pairs = [(request.query, doc) for doc in request.documents]
    with _model_lock:
        scores = _model.predict(pairs)

    ranked = sorted(
        (
            RerankResult(index=i, relevance_score=float(score))
            for i, score in enumerate(scores)
        ),
        key=lambda r: r.relevance_score,
        reverse=True,
    )
    if request.top_n is not None:
        ranked = ranked[: request.top_n]
    return RerankResponse(results=ranked)
