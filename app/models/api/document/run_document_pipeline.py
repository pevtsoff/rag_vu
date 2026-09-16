from pydantic import BaseModel


class RunDocumentPipeline(BaseModel):
    document_id: str
    pipeline_id: str
    status: str
