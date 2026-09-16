from pydantic import BaseModel


class RerunPipeline(BaseModel):
    document_id: str
    pipeline_id: str
    status: str
