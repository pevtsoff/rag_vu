"""Finds the document a ``force_upload`` acts on: the latest one with the same file name."""

from app.application.dto.upload_override import UploadOverride
from app.application.errors import AmbiguousVersioningTargetError, VersioningTargetNotFoundError
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.documents.document import Document
from app.domain.documents.versioning_override import VersioningOverride


async def find_versioning_target(
    uow: UnitOfWork, file_name: str, override: UploadOverride
) -> Document | None:
    """None without an override; raise before anything is stored when there is no target."""
    if override.mode is None:
        return None
    candidates = await uow.documents.latest_with_file_name(file_name, for_update=True)
    if override.cluster_id is not None:
        candidates = [doc for doc in candidates if doc.cluster_id == override.cluster_id]
    if not candidates:
        where = f" in cluster {override.cluster_id}" if override.cluster_id else ""
        raise VersioningTargetNotFoundError(
            f"force_upload={override.mode}: no latest document is called {file_name!r}{where}"
        )
    # create_new doesn't touch the existing documents, so any one of them is a valid target.
    if override.mode is VersioningOverride.REPLACE_LATEST and len(candidates) > 1:
        raise AmbiguousVersioningTargetError(
            file_name, [str(document.cluster_id) for document in candidates]
        )
    return candidates[0]
