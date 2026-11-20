"""Stage jobs for Celery workers (imports Docling and Transformers)."""

from datetime import timedelta
from functools import cached_property

from app.adapters.outbound.chunking.docling_hybrid_chunker import DoclingHybridChunker
from app.adapters.outbound.chunking.hybrid_chunker_factory import create_hybrid_chunker
from app.adapters.outbound.parsing.docling.docling_converter_factory import (
    create_document_converter,
)
from app.adapters.outbound.parsing.docling.docling_document_parser import DoclingDocumentParser
from app.adapters.outbound.parsing.docling.docling_image_extractor import DoclingImageExtractor
from app.adapters.outbound.parsing.docling.docling_node_builder import DoclingNodeBuilder
from app.adapters.outbound.parsing.tesseract_text_recognizer import TesseractTextRecognizer
from app.adapters.outbound.storage.local_file_storage import LocalFileStorage
from app.application.ports.clock import Clock
from app.application.use_cases.events.inbox_job_runner import InboxJobRunner
from app.application.use_cases.stages.chunk_stage_job import ChunkStageJob
from app.application.use_cases.stages.embed_stage_job import EmbedStageJob
from app.application.use_cases.stages.parse_stage_job import ParseStageJob
from app.application.use_cases.stages.stage_job import StageJob
from app.application.use_cases.stages.upload_stage_job import UploadStageJob
from app.bootstrap.infrastructure import Infrastructure


class WorkerContainer:
    def __init__(self, infrastructure: Infrastructure) -> None:
        self.infrastructure = infrastructure
        self._settings = infrastructure.settings
        self._runners: dict[str, InboxJobRunner] = {}

    def inbox_job_runner(self, consumer: str) -> InboxJobRunner:
        if consumer not in self._runners:
            self._runners[consumer] = InboxJobRunner(
                self.infrastructure.unit_of_work,
                self.infrastructure.event_registry,
                self._stage_job(consumer),
                self.infrastructure.clock,
                timedelta(seconds=self._settings.inbox_lock_timeout_seconds),
            )
        return self._runners[consumer]

    def _stage_job(self, consumer: str) -> StageJob:
        builders = {
            UploadStageJob.consumer: lambda: UploadStageJob(self._clock, self._storage),
            ParseStageJob.consumer: lambda: ParseStageJob(self._clock, self._parser),
            ChunkStageJob.consumer: lambda: ChunkStageJob(self._clock, self._chunker),
            EmbedStageJob.consumer: lambda: EmbedStageJob(
                self._clock, self.infrastructure.embedder, self._settings.embedding_batch_size
            ),
        }
        if consumer not in builders:
            raise LookupError(f"No stage job handles consumer {consumer!r}")
        return builders[consumer]()

    @property
    def _clock(self) -> Clock:
        return self.infrastructure.clock

    @cached_property
    def _storage(self) -> LocalFileStorage:
        return LocalFileStorage(self._settings.upload_path)

    @cached_property
    def _parser(self) -> DoclingDocumentParser:
        return DoclingDocumentParser(
            create_document_converter,
            DoclingNodeBuilder(),
            DoclingImageExtractor(TesseractTextRecognizer()),
        )

    @cached_property
    def _chunker(self) -> DoclingHybridChunker:
        settings = self._settings
        return DoclingHybridChunker(
            lambda: create_hybrid_chunker(
                settings.embedding_tokenizer, settings.embedding_chunk_max_tokens
            )
        )
