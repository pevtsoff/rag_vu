"""Moves documents between version clusters while keeping one latest version per cluster."""

from uuid import UUID

from app.application.errors import ClusterNotFoundError
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.documents.document import Document


class ClusterMembership:
    """Every method writes rows in the order the partial unique indexes need.

    A cluster's latest row is locked (``FOR UPDATE``) before it changes, so two documents
    joining one cluster at the same time are serialised instead of both becoming latest.
    """

    async def join_as_latest(
        self, uow: UnitOfWork, document: Document, cluster_id: UUID
    ) -> Document:
        """Make ``document`` the next and latest version of ``cluster_id``."""
        current = await self._locked_latest(uow, cluster_id)
        await self.leave(uow, document)
        current.supersede()
        await uow.documents.update(current)
        document.join_cluster(cluster_id, await uow.documents.max_version(cluster_id) + 1)
        await uow.documents.update(document)
        return current

    async def leave(self, uow: UnitOfWork, document: Document) -> None:
        """Start a cluster of its own; promote the previous version if it was the latest."""
        if document.is_alone_in_own_cluster:
            return
        old_cluster, was_latest = document.cluster_id, document.is_latest
        document.start_own_cluster()
        await uow.documents.update(document)
        if was_latest and old_cluster is not None:
            previous = await uow.documents.highest_other_version(old_cluster, document.id)
            if previous is not None:
                previous.join_cluster(old_cluster, previous.version)
                await uow.documents.update(previous)

    async def _locked_latest(self, uow: UnitOfWork, cluster_id: UUID) -> Document:
        # Under READ COMMITTED a concurrent writer may just have moved the latest flag; the
        # second read sees its committed result.
        for _ in range(2):
            latest = await uow.documents.latest_in_cluster(cluster_id, for_update=True)
            if latest is not None:
                return latest
        raise ClusterNotFoundError(f"Cluster {cluster_id} has no latest version")
