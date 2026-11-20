"""What a vector is used for; providers embed queries and passages differently."""

from enum import StrEnum


class EmbeddingTask(StrEnum):
    QUERY = "query"
    PASSAGE = "passage"
