from celery import chain

from app.models.db.pipeline import PipelineStages
from app.services.background_jobs.tasks import chunk_document_task, parse_document_task


def enqueue_pipeline(
    document_id: str, pipeline_id: str, from_stage: PipelineStages = PipelineStages.PARSING
) -> None:
    if from_stage == PipelineStages.PARSING:
        chain(
            parse_document_task.si(document_id, pipeline_id),
            chunk_document_task.si(document_id, pipeline_id),
        ).apply_async()
    elif from_stage == PipelineStages.CHUNKING:
        chunk_document_task.apply_async(args=(document_id, pipeline_id))
    else:
        raise ValueError(f"Unsupported pipeline stage: {from_stage}")
