"""Import a structured law and hand it to the chunking stage."""

import hashlib

from app.application.dto.import_law_result import ImportLawResult
from app.application.dto.law_document import LawDocument
from app.application.ports.law_source import LawSource
from app.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.use_cases.documents.producers import LAW_IMPORT_PRODUCER
from app.domain.documents.document import Document
from app.domain.documents.pipeline import Pipeline
from app.domain.documents.pipeline_stage import PipelineStage
from app.domain.events.document_parsed_event import DocumentParsedEvent
from app.domain.events.event_envelope import EventEnvelope

LAW_MIME_TYPE = "text/html"


class ImportLaw:
    """The law source already yields nodes, so the pipeline starts at chunking."""

    def __init__(self, uow_factory: UnitOfWorkFactory, source: LawSource) -> None:
        self._uow_factory = uow_factory
        self._source = source

    async def execute(self, url: str) -> ImportLawResult:
        law = await self._source.fetch(url)
        sha256 = hashlib.sha256(law.body_text.encode("utf-8")).hexdigest()
        async with self._uow_factory() as uow:
            existing = await uow.documents.get_by_sha256(sha256)
            if existing is not None:
                return ImportLawResult(existing.id, None, 0, duplicate=True)
            result = await self._store(uow, law, sha256)
            await uow.commit()
        return result

    async def _store(self, uow: UnitOfWork, law: LawDocument, sha256: str) -> ImportLawResult:
        document = _law_document(law, sha256)
        pipeline = Pipeline.start(document.id, PipelineStage.CHUNKING)
        await uow.documents.add(document)
        await uow.pipelines.add(pipeline)
        node_count = await uow.nodes.replace_for_document(document.id, law.nodes)
        event = DocumentParsedEvent(
            producer=LAW_IMPORT_PRODUCER,
            document_id=document.id,
            pipeline_id=pipeline.id,
            structure_path=None,
            node_count=node_count,
        )
        await uow.outbox.add([EventEnvelope.from_event(event)])
        return ImportLawResult(document.id, pipeline.id, node_count, duplicate=False)


def _law_document(law: LawDocument, sha256: str) -> Document:
    return Document(
        file_name=(law.title or "Law Document")[:255],
        file_path=law.url,
        size=len(law.body_text),
        sha256=sha256,
        mime_type=LAW_MIME_TYPE,
        doc_metadata={**law.metadata, "articles": law.articles, "source_url": law.url},
    )
