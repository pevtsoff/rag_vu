"""Runs the real use cases against PostgreSQL with deterministic parser/embedder fakes."""

from datetime import timedelta

from app.adapters.outbound.chunking.text_chunker import TextChunker
from app.adapters.outbound.storage.local_file_storage import LocalFileStorage
from app.application.ports.document_parser import DocumentParser
from app.application.use_cases.documents.upload_document import UploadDocument
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher
from app.application.use_cases.events.inbox_job_runner import InboxJobRunner
from app.application.use_cases.events.relay_outbox_batch import RelayOutboxBatch
from app.application.use_cases.stages.chunk_stage_job import ChunkStageJob
from app.application.use_cases.stages.embed_stage_job import EmbedStageJob
from app.application.use_cases.stages.parse_stage_job import ParseStageJob
from app.application.use_cases.stages.upload_stage_job import UploadStageJob
from app.application.use_cases.stages.version_stage_job import VersionStageJob
from app.bootstrap.infrastructure import Infrastructure
from tests.unit.fakes.fake_ports import FakeEmbedder, FakeParser, RecordingDispatcher


class PipelineRunner:
    def __init__(
        self, infrastructure: Infrastructure, parser: DocumentParser | None = None
    ) -> None:
        uow, clock = infrastructure.unit_of_work, infrastructure.clock
        routes = infrastructure.event_routes
        self.storage = LocalFileStorage(infrastructure.settings.upload_path)
        self.embedder = FakeEmbedder(dimensions=768)
        self.dispatcher = RecordingDispatcher()
        self.upload = UploadDocument(uow, self.storage, clock=clock)
        self.relay = RelayOutboxBatch(
            uow, routes, DeliveryDispatcher(self.dispatcher, routes), clock, 50
        )
        jobs = [
            UploadStageJob(clock, self.storage),
            ParseStageJob(clock, parser or FakeParser()),
            ChunkStageJob(clock, TextChunker()),
            EmbedStageJob(clock, self.embedder, batch_size=2),
            VersionStageJob(clock),
        ]
        self.runners = {
            job.consumer: InboxJobRunner(
                uow, infrastructure.event_registry, job, clock, timedelta(minutes=5)
            )
            for job in jobs
        }

    async def drain(self) -> list[str]:
        order: list[str] = []
        while await self.relay.execute():
            pending, self.dispatcher.dispatched = self.dispatcher.dispatched, []
            for route, inbox_id in pending:
                order.append(route.consumer)
                await self.runners[route.consumer].run(inbox_id)
        return order
