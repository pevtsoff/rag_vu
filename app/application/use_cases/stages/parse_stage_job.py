"""Stage 2: convert the stored file into structural nodes."""

from typing import Any

from app.application.dto.parsed_document import ParsedDocument
from app.application.ports.clock import Clock
from app.application.ports.document_parser import DocumentParser
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.stages.stage_context import StageContext
from app.application.use_cases.stages.stage_job import StageJob
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.domain_event import DomainEvent


class ParseStageJob(StageJob):
    consumer = "parsing"
    stage = PipelineStage.PARSING

    def __init__(self, clock: Clock, parser: DocumentParser) -> None:
        super().__init__(clock)
        self._parser = parser

    async def compute(self, context: StageContext) -> ParsedDocument:
        document = context.document
        return await self._parser.parse(document.file_path, document.file_name)

    async def _store(
        self,
        uow: UnitOfWork,
        context: StageContext,
        document: Document,
        pipeline: Pipeline,
        result: Any,
    ) -> DomainEvent:
        node_count = await uow.nodes.replace_for_document(document.id, result.nodes)
        document.structure_path = result.structure_path
        return DocumentParsedEvent(
            producer=self.consumer,
            document_id=document.id,
            pipeline_id=pipeline.id,
            structure_path=result.structure_path,
            node_count=node_count,
        )
