from pydantic import BaseModel


class UploadDocumentResponse(BaseModel):
    id: str
    pipeline_id: str | None
    filename: str
    status: str
    duplicate: bool = False
    cluster_id: str | None = None
    version: int | None = None
    is_latest: bool | None = None
