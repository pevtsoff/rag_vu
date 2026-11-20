"""Lifecycle status shared by pipelines and documents."""

from enum import StrEnum


class PipelineStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
