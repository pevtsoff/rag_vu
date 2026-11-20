from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.documents.invalid_stage_transition_error import InvalidStageTransitionError
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.documents.pipeline_status import PipelineStatus

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def test_stages_run_in_order() -> None:
    assert list(PipelineStage) == [
        PipelineStage.UPLOADING,
        PipelineStage.PARSING,
        PipelineStage.CHUNKING,
        PipelineStage.EMBEDDING,
    ]
    assert PipelineStage.UPLOADING.next() is PipelineStage.PARSING
    assert PipelineStage.EMBEDDING.next() is None
    assert PipelineStage.CHUNKING.preceding() == (PipelineStage.UPLOADING, PipelineStage.PARSING)


def test_unknown_stage_is_rejected() -> None:
    with pytest.raises(ValueError):
        PipelineStage("upload")


def test_completing_every_stage_succeeds_the_pipeline() -> None:
    pipeline = Pipeline.start(uuid4(), PipelineStage.UPLOADING)
    for stage in PipelineStage:
        assert pipeline.stage is stage
        pipeline.complete(stage, NOW)
    assert pipeline.status is PipelineStatus.SUCCEEDED
    assert pipeline.uploaded and pipeline.parsed and pipeline.chunked and pipeline.embedded
    assert pipeline.embedded_at == NOW


def test_start_marks_preceding_stages_complete_and_keeps_their_timestamps() -> None:
    previous = Pipeline.start(uuid4(), PipelineStage.UPLOADING)
    previous.complete(PipelineStage.UPLOADING, NOW)
    rerun = Pipeline.start(previous.document_id, PipelineStage.CHUNKING, previous)
    assert (rerun.uploaded, rerun.parsed, rerun.chunked, rerun.embedded) == (
        True,
        True,
        False,
        False,
    )
    assert rerun.uploaded_at == NOW
    assert rerun.parsed_at is None
    assert rerun.stage is PipelineStage.CHUNKING


def test_complete_rejects_a_stage_out_of_order() -> None:
    pipeline = Pipeline.start(uuid4(), PipelineStage.UPLOADING)
    with pytest.raises(InvalidStageTransitionError):
        pipeline.complete(PipelineStage.PARSING, NOW)


def test_cancelled_pipeline_cannot_advance() -> None:
    pipeline = Pipeline.start(uuid4(), PipelineStage.PARSING)
    pipeline.cancel()
    assert pipeline.status is PipelineStatus.CANCELLED
    with pytest.raises(InvalidStageTransitionError):
        pipeline.complete(PipelineStage.PARSING, NOW)


def test_fail_records_stage_and_message() -> None:
    pipeline = Pipeline.start(uuid4(), PipelineStage.PARSING)
    pipeline.fail(PipelineStage.PARSING, "boom")
    assert (pipeline.status, pipeline.error_stage, pipeline.error_message) == (
        PipelineStatus.FAILED,
        "parsing",
        "boom",
    )
