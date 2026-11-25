"""Stage 5: fingerprint the document and decide which version cluster it belongs to."""

import logging
from typing import Any

from app.application.dto.versioning_input import VersioningInput
from app.application.errors import EmptyStageResultError
from app.application.ports.clock import Clock
from app.application.ports.trace_span import TraceValue
from app.application.ports.unit_of_work import UnitOfWork
from app.application.tracing.trace_attributes import (
    VERSIONING_CHUNK_COUNT,
    VERSIONING_HAS_EMBEDDING,
    VERSIONING_IDENTIFIER,
    VERSIONING_REDACTION,
)
from app.application.use_cases.documents.cluster_membership import ClusterMembership
from app.application.use_cases.stages.stage_context import StageContext
from app.application.use_cases.stages.stage_job import StageJob
from app.domain.documents.document import IDENTIFIER_KEY, REDACTION_KEY, Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.document_versioned_event import DocumentVersionedEvent
from app.domain.events.domain_event import DomainEvent
from app.domain.versioning.document_fingerprint import DocumentFingerprint
from app.domain.versioning.embedding_average import average_embedding
from app.domain.versioning.law_identifier import law_identifier, law_redaction
from app.domain.versioning.min_hasher import MinHasher
from app.domain.versioning.version_matcher import VersionMatcher
from app.domain.versioning.versioning_decision import VersioningDecision
from app.domain.versioning.versioning_outcome import VersioningOutcome
from app.domain.versioning.versioning_source import VersioningSource
from app.domain.versioning.versioning_thresholds import VersioningThresholds

logger = logging.getLogger(__name__)
# documents.avg_embedding is vector(768): qwen3-embedding:0.6b, the only supported size for now.
FINGERPRINT_DIMENSIONS = 768
CANDIDATE_LIMIT = 5
OVERRIDE_SOURCES = frozenset({VersioningSource.FORCE_UPLOAD, VersioningSource.MANUAL})


class VersionStageJob(StageJob):
    consumer = "versioning"
    stage = PipelineStage.VERSIONING

    def __init__(self, clock: Clock, thresholds: VersioningThresholds | None = None) -> None:
        super().__init__(clock)
        self._thresholds = thresholds or VersioningThresholds()
        self._matcher = VersionMatcher(self._thresholds)
        self._min_hasher = MinHasher()
        self._membership = ClusterMembership()

    async def _load(self, uow: UnitOfWork, document: Document) -> VersioningInput:
        dimensions = await uow.chunks.embedded_dimensions(document.id)
        rows = await uow.chunks.list_embedded(document.id, dimensions) if dimensions else []
        if not rows:
            raise EmptyStageResultError(f"No embedded chunks to version document {document.id}")
        return VersioningInput([text for text, _ in rows], [v for _, v in rows], dimensions)

    async def compute(self, context: StageContext) -> DocumentFingerprint:
        data: VersioningInput = context.data
        text = "\n".join(data.texts)
        return DocumentFingerprint(
            avg_embedding=self._average(data, context.document),
            minhash=self._min_hasher.signature(text),
            identifier=law_identifier(text),
            redaction=law_redaction(text),
        )

    def trace_attributes(self, context: StageContext, result: Any) -> dict[str, TraceValue]:
        return {
            VERSIONING_CHUNK_COUNT: len(context.data.texts),
            VERSIONING_HAS_EMBEDDING: result.avg_embedding is not None,
            VERSIONING_IDENTIFIER: result.identifier or "",
            VERSIONING_REDACTION: result.redaction or "",
        }

    async def _store(
        self,
        uow: UnitOfWork,
        context: StageContext,
        document: Document,
        pipeline: Pipeline,
        result: Any,
    ) -> DomainEvent:
        await uow.documents.store_fingerprint(document.id, result)
        _remember_identity(document, result)
        decision = await self._decide(uow, document, result)
        if decision is not None:
            await self._apply(uow, document, decision)
            document.record_versioning(decision.as_metadata())
        return _versioned_event(self.consumer, document, pipeline)

    def _average(self, data: VersioningInput, document: Document) -> list[float] | None:
        if data.dimensions != FINGERPRINT_DIMENSIONS:
            logger.warning(
                "Document %s has %s-dimension vectors; only %s are fingerprinted, so it is "
                "versioned by legal identifier only.",
                document.id,
                data.dimensions,
                FINGERPRINT_DIMENSIONS,
            )
            return None
        return average_embedding(data.vectors, [float(len(text)) for text in data.texts])

    async def _decide(
        self, uow: UnitOfWork, document: Document, fingerprint: DocumentFingerprint
    ) -> VersioningDecision | None:
        """None keeps the current assignment: an override, or a rerun of a placed document."""
        if document.versioning.get("source") in OVERRIDE_SOURCES:
            return None
        if not document.is_alone_in_own_cluster or document.deleted_at is not None:
            return None
        if fingerprint.identifier:
            match = await uow.documents.latest_with_identifier(
                fingerprint.identifier, document.cluster_id, fingerprint.avg_embedding
            )
            if match is not None:
                return self._matcher.by_identifier(fingerprint, match)
        if fingerprint.avg_embedding is None:
            return VersioningDecision(VersioningOutcome.NEW_DOCUMENT, VersioningSource.NEW)
        candidates = await uow.documents.nearest_latest(
            fingerprint.avg_embedding,
            self._thresholds.max_cosine_distance,
            CANDIDATE_LIMIT,
            document.cluster_id,
        )
        return self._matcher.by_fingerprint(fingerprint, candidates)

    async def _apply(
        self, uow: UnitOfWork, document: Document, decision: VersioningDecision
    ) -> None:
        if decision.match is None:
            return
        if decision.outcome is VersioningOutcome.NEW_VERSION:
            await self._membership.join_as_latest(uow, document, decision.match.cluster_id)
        elif decision.outcome is VersioningOutcome.DUPLICATE:
            document.mark_duplicate_of(decision.match.document_id)


def _remember_identity(document: Document, fingerprint: DocumentFingerprint) -> None:
    if fingerprint.identifier:
        document.set_metadata(IDENTIFIER_KEY, fingerprint.identifier)
    if fingerprint.redaction:
        document.set_metadata(REDACTION_KEY, fingerprint.redaction)


def _versioned_event(producer: str, document: Document, pipeline: Pipeline) -> DomainEvent:
    versioning = document.versioning
    return DocumentVersionedEvent(
        producer=producer,
        document_id=document.id,
        pipeline_id=pipeline.id,
        cluster_id=document.cluster_id,
        version=document.version,
        is_latest=document.is_latest,
        outcome=str(versioning.get("outcome", "kept")),
        source=str(versioning.get("source", VersioningSource.KEPT)),
    )
