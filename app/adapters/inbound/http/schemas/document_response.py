from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_name: str
    size: int
    status: str
    mime_type: str
    doc_metadata: dict | None = None
    version: int
    cluster_id: UUID | None = None
    is_latest: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
