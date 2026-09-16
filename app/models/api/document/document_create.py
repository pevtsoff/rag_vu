from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_path: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    mime_type: str = Field(min_length=1, max_length=50)
    doc_metadata: dict | None = None
