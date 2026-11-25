"""Persistence of documents, their versions and their fingerprints."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.documents.document import Document
from app.domain.versioning.document_fingerprint import DocumentFingerprint
from app.domain.versioning.fingerprint_candidate import FingerprintCandidate


class DocumentRepository(ABC):
    @abstractmethod
    async def get(self, document_id: UUID, for_update: bool = False) -> Document | None: ...

    @abstractmethod
    async def get_by_sha256(self, sha256: str, for_update: bool = False) -> Document | None: ...

    @abstractmethod
    async def add(self, document: Document) -> None: ...

    @abstractmethod
    async def update(self, document: Document) -> None: ...

    @abstractmethod
    async def latest_with_file_name(
        self, file_name: str, for_update: bool = False
    ) -> list[Document]:
        """Latest, not deleted documents called ``file_name`` (one per cluster)."""

    @abstractmethod
    async def exists_with_file_name(self, file_name: str) -> bool:
        """True when any live (not deleted) document, of any version, is called ``file_name``."""

    @abstractmethod
    async def latest_in_cluster(
        self, cluster_id: UUID, for_update: bool = False
    ) -> Document | None: ...

    @abstractmethod
    async def highest_other_version(self, cluster_id: UUID, exclude_id: UUID) -> Document | None:
        """The live version of the cluster with the highest number, other than ``exclude_id``."""

    @abstractmethod
    async def max_version(self, cluster_id: UUID) -> int:
        """The highest live version number of the cluster, or 0 when it has none."""

    @abstractmethod
    async def store_fingerprint(self, document_id: UUID, fingerprint: DocumentFingerprint) -> None:
        """Save ``avg_embedding`` and ``minhash_sig``."""

    @abstractmethod
    async def latest_with_identifier(
        self, identifier: str, exclude_cluster_id: UUID, vector: list[float] | None
    ) -> FingerprintCandidate | None:
        """The latest version of another cluster that has the same legal identifier."""

    @abstractmethod
    async def nearest_latest(
        self, vector: list[float], max_distance: float, limit: int, exclude_cluster_id: UUID
    ) -> list[FingerprintCandidate]:
        """Latest versions of other clusters, nearest by ``avg_embedding`` first."""
