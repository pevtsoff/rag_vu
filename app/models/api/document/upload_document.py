from pydantic import BaseModel


class UploadDocument(BaseModel):
    id: str
    pipeline_id: str
    filename: str
    status: str
    duplicate: bool = False
