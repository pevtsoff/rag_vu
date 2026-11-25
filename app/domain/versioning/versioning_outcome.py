from enum import StrEnum


class VersioningOutcome(StrEnum):
    NEW_DOCUMENT = "new_document"
    NEW_VERSION = "new_version"
    DUPLICATE = "duplicate"
