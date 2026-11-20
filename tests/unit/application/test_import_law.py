from app.application.dto.law_document import LawDocument
from app.application.ports.law_source import LawSource
from app.application.use_cases.documents.import_law import ImportLaw
from app.domain.documents.parsed_node import ParsedNode
from app.domain.documents.pipeline_stage import PipelineStage
from tests.unit.fakes.in_memory_store import InMemoryStore
from tests.unit.fakes.in_memory_unit_of_work import uow_factory


class StaticLawSource(LawSource):
    async def fetch(self, url: str) -> LawDocument:
        nodes = [ParsedNode("Статья 1", "Текст.", ["Закон", "Статья 1"], "s1.a1", "article")]
        return LawDocument(url, "Закон", "Текст закона", nodes, {"number": "53-ФЗ"})


async def test_import_stores_nodes_and_starts_the_pipeline_at_chunking() -> None:
    store = InMemoryStore()
    result = await ImportLaw(uow_factory(store), StaticLawSource()).execute("https://law")

    assert not result.duplicate and result.node_count == 1
    pipeline = store.pipelines[result.pipeline_id]
    assert pipeline.stage is PipelineStage.CHUNKING and pipeline.uploaded and pipeline.parsed
    document = store.documents[result.document_id]
    assert document.file_path == "https://law" and document.doc_metadata["number"] == "53-ФЗ"
    [envelope] = store.outbox.values()
    assert envelope.event_type == "DocumentParsedEvent" and envelope.producer == "law-import"
    assert envelope.payload["structure_path"] is None


async def test_importing_the_same_text_twice_is_a_no_op() -> None:
    store = InMemoryStore()
    use_case = ImportLaw(uow_factory(store), StaticLawSource())
    first = await use_case.execute("https://law")
    second = await use_case.execute("https://law")
    assert second.duplicate and second.document_id == first.document_id
    assert len(store.outbox) == 1
