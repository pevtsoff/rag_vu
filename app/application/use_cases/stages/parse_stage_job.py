"""Stage 2: convert the stored file into structural nodes."""

import json
from collections import Counter
from typing import Any

from app.application.dto.parsed_document import ParsedDocument
from app.application.ports.clock import Clock
from app.application.ports.document_parser import DocumentParser
from app.application.ports.trace_span import TraceValue
from app.application.ports.unit_of_work import UnitOfWork
from app.application.tracing.trace_attributes import (
    PARSE_NODE_COUNT,
    PARSE_NODE_TYPES,
    PARSE_STRUCTURE_PATH,
    PARSE_TEXT_CHARS,
    PARSE_TITLE,
)
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

    def trace_attributes(self, context: StageContext, result: Any) -> dict[str, TraceValue]:
        parsed: ParsedDocument = result
        node_types = Counter(node.node_type for node in parsed.nodes)
        attributes: dict[str, TraceValue] = {
            PARSE_TITLE: parsed.title,
            PARSE_NODE_COUNT: len(parsed.nodes),
            PARSE_NODE_TYPES: json.dumps(dict(node_types.most_common()), ensure_ascii=False),
            PARSE_TEXT_CHARS: sum(len(node.text or "") for node in parsed.nodes),
        }
        if parsed.structure_path:
            attributes[PARSE_STRUCTURE_PATH] = parsed.structure_path
        return attributes

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
