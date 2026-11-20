from pydantic import BaseModel


class RerunPipelineResponse(BaseModel):
    document_id: str
    pipeline_id: str
    status: str
