"""Ordered ingestion stages."""

from enum import StrEnum


class PipelineStage(StrEnum):
    """An ingestion stage; members are declared in execution order."""

    UPLOADING = "uploading"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    VERSIONING = "versioning"

    def next(self) -> "PipelineStage | None":
        """Return the stage that follows this one, or None for the last stage."""
        stages = list(PipelineStage)
        index = stages.index(self)
        return stages[index + 1] if index + 1 < len(stages) else None

    def preceding(self) -> tuple["PipelineStage", ...]:
        """Return the stages that must be complete before this one starts."""
        stages = list(PipelineStage)
        return tuple(stages[: stages.index(self)])
