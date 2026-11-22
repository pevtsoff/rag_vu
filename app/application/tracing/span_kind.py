"""What a span represents; tracing backends render each kind differently."""

from enum import StrEnum


class SpanKind(StrEnum):
    CHAIN = "CHAIN"
    RETRIEVER = "RETRIEVER"
    RERANKER = "RERANKER"
    LLM = "LLM"
    EMBEDDING = "EMBEDDING"
