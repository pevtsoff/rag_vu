"""Dict-backed repositories that follow the port contracts of the SQL adapters."""

from datetime import datetime
from uuid import UUID, uuid4

from app.application.dto.inbox_delivery import InboxDelivery
from app.application.dto.inbox_message import InboxMessage
from app.application.errors import ConcurrencyConflictError
from app.application.ports.chunk_repository import ChunkRepository
from app.application.ports.document_repository import DocumentRepository
from app.application.ports.inbox_repository import InboxRepository
from app.application.ports.node_repository import NodeRepository
from app.application.ports.outbox_repository import OutboxRepository
from app.application.ports.pipeline_repository import PipelineRepository
from app.domain.documents.chunk import Chunk
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.document import Document
from app.domain.documents.node import Node
from app.domain.documents.parsed_node import ParsedNode
from app.domain.documents.pipeline import Pipeline
from app.domain.events.event_envelope import EventEnvelope
from app.domain.versioning.document_fingerprint import DocumentFingerprint
from app.domain.versioning.fingerprint_candidate import FingerprintCandidate
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.inbox_record import InboxRecord


class InMemoryDocumentRepository(DocumentRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get(self, document_id: UUID, for_update: bool = False) -> Document | None:
        return self._store.documents.get(document_id)

    async def get_by_sha256(self, sha256: str, for_update: bool = False) -> Document | None:
        return next((d for d in self._store.documents.values() if d.sha256 == sha256), None)

    async def add(self, document: Document) -> None:
        if document.sha256 and await self.get_by_sha256(document.sha256):
            raise ConcurrencyConflictError("duplicate sha256")
        self._check_versions(document)
        self._store.documents[document.id] = document

    async def update(self, document: Document) -> None:
        self._check_versions(document)
        self._store.documents[document.id] = document

    async def latest_with_file_name(
        self, file_name: str, for_update: bool = False
    ) -> list[Document]:
        return [d for d in self._latest() if d.file_name == file_name]

    async def exists_with_file_name(self, file_name: str) -> bool:
        return any(
            d.file_name == file_name and d.deleted_at is None
            for d in self._store.documents.values()
        )

    async def latest_in_cluster(
        self, cluster_id: UUID, for_update: bool = False
    ) -> Document | None:
        return next((d for d in self._latest() if d.cluster_id == cluster_id), None)

    async def highest_other_version(self, cluster_id: UUID, exclude_id: UUID) -> Document | None:
        others = [d for d in self._live(cluster_id) if d.id != exclude_id]
        return max(others, key=lambda d: d.version, default=None)

    async def max_version(self, cluster_id: UUID) -> int:
        return max((d.version for d in self._live(cluster_id)), default=0)

    async def store_fingerprint(self, document_id: UUID, fingerprint: DocumentFingerprint) -> None:
        self._store.fingerprints[document_id] = fingerprint

    async def latest_with_identifier(
        self, identifier: str, exclude_cluster_id: UUID, vector: list[float] | None
    ) -> FingerprintCandidate | None:
        for document in reversed(self._latest()):
            if (
                document.cluster_id != exclude_cluster_id
                and (document.doc_metadata or {}).get("identifier") == identifier
            ):
                return self._candidate(document, vector)
        return None

    async def nearest_latest(
        self, vector: list[float], max_distance: float, limit: int, exclude_cluster_id: UUID
    ) -> list[FingerprintCandidate]:
        candidates = [
            self._candidate(document, vector)
            for document in self._latest()
            if document.cluster_id != exclude_cluster_id
            and self._store.fingerprints.get(document.id)
            and self._store.fingerprints[document.id].avg_embedding is not None
        ]
        close = [c for c in candidates if 2 * (1 - (c.semantic_similarity or 0)) <= max_distance]
        return sorted(close, key=lambda c: -(c.semantic_similarity or 0))[:limit]

    def _candidate(self, document: Document, vector: list[float] | None) -> FingerprintCandidate:
        fingerprint = self._store.fingerprints.get(document.id)
        semantic = None
        if vector is not None and fingerprint and fingerprint.avg_embedding is not None:
            semantic = (1 + sum(a * b for a, b in zip(vector, fingerprint.avg_embedding))) / 2
        return FingerprintCandidate(
            document_id=document.id,
            cluster_id=document.cluster_id,
            version=document.version,
            semantic_similarity=semantic,
            minhash=fingerprint.minhash if fingerprint else None,
            identifier=(document.doc_metadata or {}).get("identifier"),
        )

    def _latest(self) -> list[Document]:
        return [d for d in self._store.documents.values() if d.is_latest and d.deleted_at is None]

    def _live(self, cluster_id: UUID) -> list[Document]:
        return [
            d
            for d in self._store.documents.values()
            if d.cluster_id == cluster_id and d.deleted_at is None
        ]

    def _check_versions(self, document: Document) -> None:
        """The partial unique indexes on (cluster_id) WHERE is_latest and (cluster_id, version)."""
        if document.deleted_at is not None:
            return
        for other in self._live(document.cluster_id):
            if other.id == document.id:
                continue
            if other.version == document.version or (other.is_latest and document.is_latest):
                raise ConcurrencyConflictError(f"version conflict in cluster {document.cluster_id}")


class InMemoryPipelineRepository(PipelineRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get(self, pipeline_id: UUID, for_update: bool = False) -> Pipeline | None:
        return self._store.pipelines.get(pipeline_id)

    async def get_active(self, document_id: UUID, for_update: bool = False) -> Pipeline | None:
        return next((p for p in self._of(document_id) if p.is_active), None)

    async def get_latest(self, document_id: UUID) -> Pipeline | None:
        pipelines = self._of(document_id)
        return pipelines[-1] if pipelines else None

    async def list_for_document(self, document_id: UUID) -> list[Pipeline]:
        return list(reversed(self._of(document_id)))

    async def add(self, pipeline: Pipeline) -> None:
        if pipeline.is_active and await self.get_active(pipeline.document_id):
            raise ConcurrencyConflictError("one in-progress pipeline per document")
        self._store.pipelines[pipeline.id] = pipeline

    async def update(self, pipeline: Pipeline) -> None:
        self._store.pipelines[pipeline.id] = pipeline

    def _of(self, document_id: UUID) -> list[Pipeline]:
        return [p for p in self._store.pipelines.values() if p.document_id == document_id]


class InMemoryNodeRepository(NodeRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def replace_for_document(self, document_id: UUID, nodes: list[ParsedNode]) -> int:
        old = {i for i, n in self._store.nodes.items() if n.document_id == document_id}
        for chunk_id in [i for i, c in self._store.chunks.items() if c.node_id in old]:
            del self._store.chunks[chunk_id]
        for node_id in old:
            del self._store.nodes[node_id]
        for parsed in nodes:
            node = Node(
                document_id=document_id,
                node_type=parsed.node_type,
                title=parsed.title,
                text=parsed.text,
                breadcrumbs=parsed.breadcrumbs,
                path=parsed.path,
            )
            self._store.nodes[node.id] = node
        return len(nodes)

    async def list_with_text(self, document_id: UUID) -> list[Node]:
        nodes = [
            n for n in self._store.nodes.values() if n.document_id == document_id and n.has_text
        ]
        return sorted(nodes, key=lambda node: node.path or "")

    async def get_with_document_title(self, node_id: UUID) -> tuple[Node, str] | None:
        node = self._store.nodes.get(node_id)
        if node is None:
            return None
        return node, self._store.documents[node.document_id].file_name


class InMemoryChunkRepository(ChunkRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def replace_for_document(self, document_id: UUID, chunks: list[ChunkDraft]) -> int:
        for chunk_id in [c.id for c in self._document_chunks(document_id)]:
            del self._store.chunks[chunk_id]
        for draft in chunks:
            chunk = Chunk(uuid4(), draft.node_id, draft.position, draft.text)
            self._store.chunks[chunk.id] = chunk
        return len(chunks)

    async def list_for_document(self, document_id: UUID) -> list[Chunk]:
        return self._document_chunks(document_id)

    async def count_for_document(self, document_id: UUID) -> int:
        return len(self._document_chunks(document_id))

    async def store_embeddings(self, vectors: dict[UUID, list[float]], dimensions: int) -> None:
        for chunk_id, vector in vectors.items():
            self._store.vectors[chunk_id] = (dimensions, vector)

    async def list_embedded(
        self, document_id: UUID, dimensions: int
    ) -> list[tuple[str, list[float]]]:
        return [
            (chunk.text, self._store.vectors[chunk.id][1])
            for chunk in self._document_chunks(document_id)
            if self._store.vectors.get(chunk.id, (None,))[0] == dimensions
        ]

    async def embedded_dimensions(self, document_id: UUID) -> int | None:
        for chunk in self._document_chunks(document_id):
            if chunk.id in self._store.vectors:
                return self._store.vectors[chunk.id][0]
        return None

    def _document_chunks(self, document_id: UUID) -> list[Chunk]:
        nodes = {i for i, n in self._store.nodes.items() if n.document_id == document_id}
        return [c for c in self._store.chunks.values() if c.node_id in nodes]


class InMemoryOutboxRepository(OutboxRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, envelopes: list[EventEnvelope]) -> None:
        for envelope in envelopes:
            self._store.outbox[envelope.event_id] = envelope

    async def lock_pending(self, limit: int) -> list[EventEnvelope]:
        pending = [e for i, e in self._store.outbox.items() if i not in self._store.published]
        return sorted(pending, key=lambda envelope: envelope.occurred_at)[:limit]

    async def mark_published(self, event_ids: list[UUID], at: datetime) -> None:
        self._store.published.update(event_ids)


class InMemoryInboxRepository(InboxRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def receive(self, envelope: EventEnvelope, consumer: str, at: datetime) -> UUID | None:
        if any(
            r.envelope.event_id == envelope.event_id and r.consumer == consumer
            for r in self._store.inbox.values()
        ):
            return None
        record = InboxRecord(uuid4(), consumer, envelope, received_at=at)
        self._store.inbox[record.id] = record
        return record.id

    async def mark_dispatched(self, inbox_ids: list[UUID], at: datetime) -> None:
        for inbox_id in inbox_ids:
            self._store.inbox[inbox_id].dispatched_at = at

    async def claim(
        self, inbox_id: UUID, lock_token: UUID, now: datetime, locked_until: datetime
    ) -> InboxMessage | None:
        record = self._store.inbox.get(inbox_id)
        if record is None or not (record.status == "RECEIVED" or _abandoned(record, now)):
            return None
        record.status, record.lock_token, record.locked_until = (
            "PROCESSING",
            lock_token,
            locked_until,
        )
        record.attempts += 1
        return InboxMessage(
            record.id, record.consumer, record.envelope, lock_token, record.attempts
        )

    async def complete(self, inbox_id: UUID, lock_token: UUID, at: datetime) -> bool:
        record = self._store.inbox[inbox_id]
        if record.status != "PROCESSING" or record.lock_token != lock_token:
            return False
        record.status, record.processed_at, record.locked_until = "PROCESSED", at, None
        return True

    async def fail(self, inbox_id: UUID, lock_token: UUID, error: str, at: datetime) -> None:
        record = self._store.inbox[inbox_id]
        if record.status == "PROCESSING" and record.lock_token == lock_token:
            record.status, record.last_error, record.locked_until = "FAILED", error, None

    async def lock_redeliverable(
        self, now: datetime, dispatched_before: datetime, limit: int
    ) -> list[InboxDelivery]:
        due = [
            r
            for r in self._store.inbox.values()
            if (r.status == "RECEIVED" or _abandoned(r, now))
            and (r.dispatched_at or r.received_at) < dispatched_before
        ][:limit]
        await self.mark_dispatched([r.id for r in due], now)
        return [InboxDelivery(r.id, r.consumer) for r in due]

    async def release_orphaned_locks(self, now: datetime, limit: int) -> list[InboxDelivery]:
        stuck = [r for r in self._store.inbox.values() if r.status == "PROCESSING"][:limit]
        for record in stuck:
            record.status, record.locked_until, record.dispatched_at = "RECEIVED", None, now
        return [InboxDelivery(r.id, r.consumer) for r in stuck]


def _abandoned(record: InboxRecord, now: datetime) -> bool:
    return (
        record.status == "PROCESSING"
        and record.locked_until is not None
        and record.locked_until < now
    )
