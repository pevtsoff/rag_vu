from enum import StrEnum


class VersioningChange(StrEnum):
    """Manual fixes of a document's cluster: ``POST /documents/{id}/versioning``."""

    CREATE_NEW = "create_new"  # split it out into a cluster of its own
    JOIN = "join"  # make it the latest version of another cluster
