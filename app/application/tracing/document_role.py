"""Which list of passages a span records."""

from enum import StrEnum


class DocumentRole(StrEnum):
    RETRIEVED = "retrieved"
    RERANK_INPUT = "rerank_input"
    RERANK_OUTPUT = "rerank_output"
