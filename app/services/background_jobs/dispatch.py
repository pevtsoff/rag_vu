from app.models.db.pipeline import PipelineStages
from app.services.background_jobs.tasks import chunk_document_task, start_parsing_task


def enqueue_pipeline(
    document_id: str, pipeline_id: str, from_stage: PipelineStages = PipelineStages.PARSING
) -> None:
    if from_stage == PipelineStages.PARSING:
        start_parsing_task.apply_async(args=(document_id, pipeline_id), queue="upload")
    elif from_stage == PipelineStages.CHUNKING:
        chunk_document_task.apply_async(args=(document_id, pipeline_id), queue="chunking")
    else:
        raise ValueError(f"Unsupported pipeline stage: {from_stage}")
