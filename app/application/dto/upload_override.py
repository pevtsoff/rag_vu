from dataclasses import dataclass
from uuid import UUID

from app.domain.documents.versioning_override import VersioningOverride


@dataclass(frozen=True)
class UploadOverride:
    """``force_upload`` and the optional ``cluster_id`` that disambiguates its target."""

    mode: VersioningOverride | None = None
    cluster_id: UUID | None = None
