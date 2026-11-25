"""Fix a wrong versioning decision after the fact."""

from uuid import UUID

from app.application.errors import DocumentNotFoundError
from app.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.use_cases.documents.cluster_membership import ClusterMembership
from app.domain.documents.document import Document
from app.domain.documents.versioning_change import VersioningChange
from app.domain.versioning.versioning_source import VersioningSource


class ChangeDocumentVersioning:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory
        self._membership = ClusterMembership()

    async def execute(
        self, document_id: UUID, change: VersioningChange, cluster_id: UUID | None = None
    ) -> Document:
        if change is VersioningChange.JOIN and cluster_id is None:
            raise ValueError("Joining a cluster needs its cluster_id")
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id, for_update=True)
            if document is None or document.deleted_at is not None:
                raise DocumentNotFoundError(f"Document {document_id} not found")
            if change is VersioningChange.CREATE_NEW:
                await self._split(uow, document)
            elif document.cluster_id != cluster_id:
                await self._membership.join_as_latest(uow, document, cluster_id)
            _record(document, change)
            await uow.documents.update(document)
            await uow.commit()
        return document

    async def _split(self, uow: UnitOfWork, document: Document) -> None:
        await self._membership.leave(uow, document)
        # A document marked as a duplicate is alone but not latest; splitting makes it a
        # document in its own right.
        document.clear_duplicate()
        document.start_own_cluster()


def _record(document: Document, change: VersioningChange) -> None:
    document.record_versioning(
        {
            "source": str(VersioningSource.MANUAL),
            "mode": str(change),
            "cluster_id": str(document.cluster_id),
            "version": document.version,
        }
    )
