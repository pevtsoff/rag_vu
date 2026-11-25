from uuid import UUID

from pydantic import BaseModel, model_validator

from app.domain.documents.versioning_change import VersioningChange


class VersioningRequest(BaseModel):
    mode: VersioningChange
    cluster_id: UUID | None = None

    @model_validator(mode="after")
    def _join_needs_cluster(self) -> "VersioningRequest":
        if self.mode is VersioningChange.JOIN and self.cluster_id is None:
            raise ValueError("mode=join needs cluster_id")
        return self
