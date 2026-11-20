"""Wires the real use cases to in-memory fakes so whole pipelines run in a unit test."""

from datetime import timedelta

from app.application.ports.tracer import Tracer
from app.application.tracing.null_tracer import NullTracer
from app.application.tracing.traced_embedder import TracedEmbedder
from app.application.use_cases.documents.upload_document import UploadDocument
from app.application.use_cases.events.default_event_routes import default_event_routes
from app.application.use_cases.events.delivery_dispatcher import DeliveryDispatcher
from app.application.use_cases.events.inbox_job_runner import InboxJobRunner
from app.application.use_cases.events.relay_outbox_batch import RelayOutboxBatch
from app.application.use_cases.stages.chunk_stage_job import ChunkStageJob
from app.application.use_cases.stages.embed_stage_job import EmbedStageJob
from app.application.use_cases.stages.parse_stage_job import ParseStageJob
from app.application.use_cases.stages.upload_stage_job import UploadStageJob
from app.domain.events.default_event_registry import default_event_registry
from tests.unit.fakes.fake_clock import FakeClock
from tests.unit.fakes.fake_ports import (
    FakeChunker,
    FakeEmbedder,
    FakeParser,
    FakeStorage,
    RecordingDispatcher,
)
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory


class PipelineHarness:
    def __init__(self, parser: FakeParser | None = None, tracer: Tracer | None = None) -> None:
        tracer = tracer or NullTracer()
        self.store = InMemoryStore()
        self.uow = uow_factory(self.store)
        self.clock = FakeClock()
        self.storage = FakeStorage()
        self.parser = parser or FakeParser()
        self.chunker = FakeChunker()
        self.embedder = FakeEmbedder()
        self.dispatcher = RecordingDispatcher()
        self.routes = default_event_routes()
        self.upload = UploadDocument(self.uow, self.storage, tracer)
        self.relay = RelayOutboxBatch(
            self.uow, self.routes, DeliveryDispatcher(self.dispatcher, self.routes), self.clock, 100
        )
        jobs = [
            UploadStageJob(self.clock, self.storage),
            ParseStageJob(self.clock, self.parser),
            ChunkStageJob(self.clock, self.chunker),
            EmbedStageJob(
                self.clock, TracedEmbedder(self.embedder, tracer, "fake-embed"), batch_size=2
            ),
        ]
        self.runners = {
            job.consumer: InboxJobRunner(
                self.uow, default_event_registry(), job, self.clock, timedelta(minutes=5), tracer
            )
            for job in jobs
        }

    async def drain(self) -> list[str]:
        """Relay and run dispatched jobs until no new work appears; return run order."""
        order: list[str] = []
        while await self.relay.execute():
            pending, self.dispatcher.dispatched = self.dispatcher.dispatched, []
            for route, inbox_id in pending:
                order.append(route.consumer)
                await self.runners[route.consumer].run(inbox_id)
        return order
