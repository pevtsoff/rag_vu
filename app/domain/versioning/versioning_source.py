from enum import StrEnum


class VersioningSource(StrEnum):
    """Why a document has its cluster: recorded in ``doc_metadata.versioning.source``."""

    IDENTIFIER = "identifier"
    FINGERPRINT = "fingerprint"
    NEW = "new"
    FORCE_UPLOAD = "force_upload"
    MANUAL = "manual"
    KEPT = "kept"
