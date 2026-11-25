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
    parsed: bool
    chunked: bool
    embedded: bool
    versioned: bool = False
    uploaded_at: datetime | None
    parsed_at: datetime | None
    chunked_at: datetime | None
    embedded_at: datetime | None
    versioned_at: datetime | None = None
    error_message: str | None
    error_stage: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
