"""Manual overrides of the automatic version assignment."""

from enum import StrEnum


class VersioningOverride(StrEnum):
    """``force_upload`` values of ``POST /documents/upload``."""

    REPLACE_LATEST = "replace_latest"
    CREATE_NEW = "create_new"
