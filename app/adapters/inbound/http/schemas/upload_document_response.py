from pydantic import BaseModel


class UploadDocumentResponse(BaseModel):
    id: str
    pipeline_id: str | None
    filename: str
    status: str
    duplicate: bool = False
