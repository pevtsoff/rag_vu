from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PipelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    stage: str | None
    status: str
    uploaded: bool
    last_uploaded: datetime | None
    parsed: bool
    last_parsed: datetime | None
    chunked: bool
    last_chunked: datetime | None
    uploaded_at: datetime | None
    parsed_at: datetime | None
    chunked_at: datetime | None
    error_message: str | None
    error_stage: str | None
    created_at: datetime
    updated_at: datetime
