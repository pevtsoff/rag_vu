"""Tests for generic document parsing and pipeline reruns."""

import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

# The test container may omit the upload extra even though it is a runtime
# dependency. FastAPI only checks these symbols while registering the route.
try:
    import python_multipart  # noqa: F401
except ImportError:
    multipart_module = types.ModuleType("multipart")
    multipart_module.__version__ = "0.0.18"
    multipart_submodule = types.ModuleType("multipart.multipart")
    multipart_submodule.parse_options_header = lambda *_args, **_kwargs: None
    sys.modules.setdefault("multipart", multipart_module)
    sys.modules.setdefault("multipart.multipart", multipart_submodule)

try:
    import celery  # noqa: F401
except ImportError:
    celery_module = types.ModuleType("celery")

    class FakeCelery:
        conf = SimpleNamespace(update=lambda **_settings: None)

        def __init__(self, *_args, **_kwargs):
            pass

        def task(self, **_options):
            return lambda function: function

    celery_module.Celery = FakeCelery
    celery_module.chain = lambda *_tasks: None
    sys.modules.setdefault("celery", celery_module)

try:
    import docling.document_converter  # noqa: F401
except ImportError:
    docling_module = types.ModuleType("docling")
    docling_module.__path__ = []
    datamodel_module = types.ModuleType("docling.datamodel")
    datamodel_module.__path__ = []
    base_models_module = types.ModuleType("docling.datamodel.base_models")
    base_models_module.InputFormat = SimpleNamespace(PDF="pdf")
    pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")

    class FakePdfPipelineOptions:
        pass

    class FakeTesseractCliOcrOptions:
        def __init__(self, **_kwargs):
            pass

    class FakeHeadingHierarchyOptions:
        pass

    pipeline_options_module.HeadingHierarchyOptions = FakeHeadingHierarchyOptions
    pipeline_options_module.PdfPipelineOptions = FakePdfPipelineOptions
    pipeline_options_module.TesseractCliOcrOptions = FakeTesseractCliOcrOptions
    converter_module = types.ModuleType("docling.document_converter")
    converter_module.DocumentConverter = lambda: None
    converter_module.PdfFormatOption = lambda **_kwargs: SimpleNamespace()
    sys.modules.setdefault("docling", docling_module)
    sys.modules.setdefault("docling.datamodel", datamodel_module)
    sys.modules.setdefault("docling.datamodel.base_models", base_models_module)
    sys.modules.setdefault("docling.datamodel.pipeline_options", pipeline_options_module)
    sys.modules.setdefault("docling.document_converter", converter_module)

from docling.datamodel import pipeline_options as pipeline_options_module

if not hasattr(pipeline_options_module, "HeadingHierarchyOptions"):
    pipeline_options_module.HeadingHierarchyOptions = lambda **_kwargs: SimpleNamespace()

try:
    import docling_core.types.doc  # noqa: F401
except ImportError:
    docling_core_module = types.ModuleType("docling_core")
    docling_core_module.__path__ = []
    types_module = types.ModuleType("docling_core.types")
    types_module.__path__ = []
    doc_module = types.ModuleType("docling_core.types.doc")
    doc_module.ImageRefMode = SimpleNamespace(PLACEHOLDER="placeholder")
    sys.modules.setdefault("docling_core", docling_core_module)
    sys.modules.setdefault("docling_core.types", types_module)
    sys.modules.setdefault("docling_core.types.doc", doc_module)

from app.models.db.document import Document
from app.models.db.pipeline import Pipeline, PipelineStages, PipelineStatus
from app.services.api.documents import rerun_stage as rerun_service
from app.services.api.documents import upload_document as upload_service
from app.services import embeddings as embeddings_service
from app.services.chunking import chunking as chunking_service
from app.services.chunking.chunking import make_chunks
from app.services.parser import parser as parser_service
from app.services.parser.parser import (
    build_nodes_from_docling,
    parse_document,
)


class TestDoclingParser(unittest.TestCase):
    def test_returns_native_docling_document_without_markdown_export(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "law.pdf"
            path.write_bytes(b"fixture")
            converter_module = types.ModuleType("docling.document_converter")
            converter_module.DocumentConverter = lambda **_kwargs: SimpleNamespace(
                convert=lambda _: SimpleNamespace(
                    document=SimpleNamespace(
                        name="Law title",
                    )
                )
            )
            base_models_module = types.ModuleType("docling.datamodel.base_models")
            base_models_module.InputFormat = SimpleNamespace(PDF="pdf")
            pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")

            class FakePdfPipelineOptions:
                pass

            class FakeTesseractCliOcrOptions:
                def __init__(self, **_kwargs):
                    pass

            pipeline_options_module.PdfPipelineOptions = FakePdfPipelineOptions
            pipeline_options_module.TesseractCliOcrOptions = FakeTesseractCliOcrOptions
            converter_module.PdfFormatOption = lambda **_kwargs: SimpleNamespace()
            docling_module = types.ModuleType("docling")
            datamodel_module = types.ModuleType("docling.datamodel")
            datamodel_module.__path__ = []
            with (
                patch.dict(
                    sys.modules,
                    {
                        "docling": docling_module,
                        "docling.datamodel": datamodel_module,
                        "docling.datamodel.base_models": base_models_module,
                        "docling.datamodel.pipeline_options": pipeline_options_module,
                        "docling.document_converter": converter_module,
                    },
                ),
                patch.object(
                    parser_service, "DocumentConverter", converter_module.DocumentConverter
                ),
            ):
                title, structured_document = parse_document(path)

        self.assertEqual(title, "Law title")
        self.assertIsNotNone(structured_document)

    def test_native_headings_build_page_section_hierarchy(self):
        def item(label, text, parent=None, page=2):
            return SimpleNamespace(
                label=label,
                text=text,
                self_ref=f"#/{text}",
                parent=(
                    SimpleNamespace(resolve=lambda doc, value=parent: value) if parent else None
                ),
                prov=[SimpleNamespace(page_no=page)],
            )

        section = item("section_header", "Раздел I")
        article = item("section_header", "Статья 1", parent=section)
        document = SimpleNamespace(
            iterate_items=lambda **_: iter(
                [
                    (section, 0),
                    (item("text", "Section body", parent=section), 1),
                    (article, 1),
                    (item("text", "Article body", parent=article), 2),
                ]
            )
        )
        nodes = build_nodes_from_docling(document, "Law")
        self.assertEqual(nodes[0].breadcrumbs, ["Law", "Page 2", "Раздел I"])
        self.assertEqual(nodes[0].path, "p000002.h1_razdel_i")
        self.assertEqual(nodes[1].breadcrumbs, ["Law", "Page 2", "Раздел I", "Статья 1"])
        self.assertEqual(nodes[1].path, "p000002.h1_razdel_i.h1_statya_1")

    def test_plain_text_legal_heading_builds_article_parent(self):
        def item(label, text, parent=None):
            return SimpleNamespace(
                label=label,
                text=text,
                self_ref=f"#/{text}",
                parent=(
                    SimpleNamespace(resolve=lambda doc, value=parent: value) if parent else None
                ),
                prov=[SimpleNamespace(page_no=2)],
            )

        article = item("text", "Статья 1. Воинская обязанность")
        body = item("text", "Воинская обязанность граждан предусматривает:", parent=article)
        document = SimpleNamespace(
            iterate_items=lambda **_: iter([(article, 0), (body, 1)])
        )

        nodes = build_nodes_from_docling(document, "Law")

        self.assertEqual([node.node_type for node in nodes], ["article"])
        self.assertEqual(nodes[0].title, "Статья 1. Воинская обязанность")
        self.assertIn("Воинская обязанность граждан", nodes[0].text)
        self.assertEqual(nodes[0].breadcrumbs, ["Law", "Page 2", article.text])

    def test_rejects_missing_input(self):
        with self.assertRaisesRegex(FileNotFoundError, "does not exist"):
            parse_document("/missing/input.pdf")


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, document):
        self.document = document
        self.added = []
        self.commits = 0

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        value = None if entity is Pipeline else self.document
        return FakeResult(value)

    def add(self, value):
        if isinstance(value, Pipeline) and value.id is None:
            value.id = uuid4()
        self.added.append(value)

    async def commit(self):
        self.commits += 1


class ActivePipelineSession(FakeSession):
    def __init__(self, document, pipeline):
        super().__init__(document)
        self.pipeline = pipeline

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        return FakeResult(self.pipeline if entity is Pipeline else self.document)


class FakePdfUpload:
    filename = "law-copy.pdf"
    content_type = "application/pdf"

    def __init__(self):
        self.read_count = 0

    async def read(self, _size):
        self.read_count += 1
        return b"pdf data" if self.read_count == 1 else b""


class TestPipelineRerun(unittest.IsolatedAsyncioTestCase):
    async def test_parsing_rerun_enqueues_full_pipeline(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="SUCCEEDED")
        session = FakeSession(document)
        with patch("app.services.api.documents.common.enqueue_pipeline") as enqueue:
            response = await rerun_service.rerun_pipeline_from_stage(
                str(document.id), PipelineStages.PARSING, session, force_run=True
            )

        pipeline = session.added[0]
        self.assertEqual(pipeline.stage, PipelineStages.PARSING)
        self.assertEqual(pipeline.status, PipelineStatus.IN_PROGRESS)
        self.assertEqual(document.status, PipelineStatus.IN_PROGRESS)
        enqueue.assert_called_once_with(str(document.id), str(pipeline.id), from_stage="parsing")
        self.assertEqual(response.pipeline_id, str(pipeline.id))

    async def test_rerun_reuses_active_pipeline_without_force(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="IN_PROGRESS")
        active = Pipeline(
            id=uuid4(), document_id=document.id, stage=PipelineStages.PARSING,
            status=PipelineStatus.IN_PROGRESS,
        )
        session = ActivePipelineSession(document, active)
        with patch("app.services.api.documents.common.enqueue_pipeline") as enqueue:
            response = await rerun_service.rerun_pipeline_from_stage(
                str(document.id), PipelineStages.PARSING, session
            )

        self.assertEqual(response.pipeline_id, str(active.id))
        self.assertEqual(session.added, [])
        enqueue.assert_not_called()

    async def test_force_rerun_cancels_active_and_enqueues_new_pipeline(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="IN_PROGRESS")
        active = Pipeline(
            id=uuid4(), document_id=document.id, stage=PipelineStages.PARSING,
            status=PipelineStatus.IN_PROGRESS,
        )
        session = ActivePipelineSession(document, active)
        with patch("app.services.api.documents.common.enqueue_pipeline") as enqueue:
            response = await rerun_service.rerun_pipeline_from_stage(
                str(document.id), PipelineStages.PARSING, session, force_run=True
            )

        replacement = session.added[0]
        self.assertEqual(active.status, PipelineStatus.CANCELLED)
        self.assertEqual(replacement.status, PipelineStatus.IN_PROGRESS)
        self.assertNotEqual(response.pipeline_id, str(active.id))
        enqueue.assert_called_once_with(
            str(document.id), str(replacement.id), from_stage="parsing"
        )

    async def test_chunking_rerun_only_enqueues_chunking(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="SUCCEEDED")
        session = FakeSession(document)
        with patch("app.services.api.documents.common.enqueue_pipeline") as enqueue:
            await rerun_service.rerun_pipeline_from_stage(
                str(document.id), PipelineStages.CHUNKING, session, force_run=True
            )

        self.assertEqual(session.added[0].stage, PipelineStages.CHUNKING)
        self.assertEqual(session.added[0].status, PipelineStatus.IN_PROGRESS)
        enqueue.assert_called_once_with(
            str(document.id), str(session.added[0].id), from_stage="chunking"
        )

    async def test_rerun_without_active_pipeline_returns_conflict(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="SUCCEEDED")
        with self.assertRaises(HTTPException) as raised:
            await rerun_service.rerun_pipeline_from_stage(
                str(document.id), PipelineStages.PARSING, FakeSession(document)
            )
        self.assertEqual(raised.exception.status_code, 409)

    async def test_unknown_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            PipelineStages("upload")

    async def test_missing_document_is_404(self):
        with self.assertRaises(HTTPException) as raised:
            await rerun_service.rerun_pipeline_from_stage(
                str(uuid4()), PipelineStages.PARSING, FakeSession(None)
            )
        self.assertEqual(raised.exception.status_code, 404)

    async def test_upload_creates_pipeline_and_queues_parsing(self):
        class FakeUpload:
            filename = "law.pdf"
            content_type = "application/pdf"

            def __init__(self):
                self.read_count = 0

            async def read(self, _size):
                self.read_count += 1
                return b"pdf data" if self.read_count == 1 else b""

        with TemporaryDirectory() as directory:
            session = FakeSession(None)
            with (
                patch.object(upload_service.settings, "upload_path", directory),
                patch("app.services.api.documents.common.enqueue_pipeline") as enqueue,
            ):
                response = await upload_service.upload_document(FakeUpload(), session)

            document = next(item for item in session.added if isinstance(item, Document))
            pipeline = next(item for item in session.added if isinstance(item, Pipeline))
            self.assertEqual(response.status, PipelineStatus.IN_PROGRESS)
            self.assertEqual(document.size, len(b"pdf data"))
            self.assertTrue(Path(document.file_path).is_file())
            self.assertEqual(pipeline.stage, PipelineStages.PARSING)
            self.assertEqual(pipeline.status, PipelineStatus.IN_PROGRESS)
            self.assertIsNotNone(pipeline.uploaded_at)
            enqueue.assert_called_once_with(
                str(document.id), str(pipeline.id), from_stage="parsing"
            )

    async def test_duplicate_upload_reuses_active_pipeline_without_force(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="IN_PROGRESS")
        active = Pipeline(
            id=uuid4(), document_id=document.id, stage=PipelineStages.PARSING,
            status=PipelineStatus.IN_PROGRESS,
        )

        with TemporaryDirectory() as directory:
            session = ActivePipelineSession(document, active)
            with (
                patch.object(upload_service.settings, "upload_path", directory),
                patch("app.services.api.documents.common.enqueue_pipeline") as enqueue,
            ):
                response = await upload_service.upload_document(FakePdfUpload(), session)

        self.assertTrue(response.duplicate)
        self.assertEqual(response.pipeline_id, str(active.id))
        self.assertEqual(session.added, [])
        enqueue.assert_not_called()

    async def test_duplicate_upload_without_active_pipeline_creates_one(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="SUCCEEDED")
        with TemporaryDirectory() as directory:
            session = FakeSession(document)
            with (
                patch.object(upload_service.settings, "upload_path", directory),
                patch("app.services.api.documents.common.enqueue_pipeline") as enqueue,
            ):
                response = await upload_service.upload_document(FakePdfUpload(), session)

        self.assertTrue(response.duplicate)
        pipeline = session.added[0]
        self.assertEqual(response.pipeline_id, str(pipeline.id))
        self.assertEqual(pipeline.status, PipelineStatus.IN_PROGRESS)
        enqueue.assert_called_once_with(
            str(document.id), str(pipeline.id), from_stage="parsing"
        )

    async def test_force_duplicate_upload_cancels_active_and_queues_new_pipeline(self):
        document = Document(id=uuid4(), file_name="law.pdf", status="IN_PROGRESS")
        active = Pipeline(
            id=uuid4(), document_id=document.id, stage=PipelineStages.PARSING,
            status=PipelineStatus.IN_PROGRESS,
        )

        with TemporaryDirectory() as directory:
            session = ActivePipelineSession(document, active)
            with (
                patch.object(upload_service.settings, "upload_path", directory),
                patch("app.services.api.documents.common.enqueue_pipeline") as enqueue,
            ):
                response = await upload_service.upload_document(
                    FakePdfUpload(), session, force_run=True
                )

        replacement = session.added[0]
        self.assertTrue(response.duplicate)
        self.assertEqual(active.status, PipelineStatus.CANCELLED)
        self.assertEqual(replacement.status, PipelineStatus.IN_PROGRESS)
        self.assertEqual(response.pipeline_id, str(replacement.id))
        enqueue.assert_called_once_with(
            str(document.id), str(replacement.id), from_stage="parsing"
        )


class TestGenericDocumentChunking(unittest.TestCase):
    def test_generic_docling_node_can_be_chunked(self):
        node = SimpleNamespace(
            id=uuid4(),
            text="# Law\n\nGeneral document text.",
            breadcrumbs=["law.pdf"],
        )
        chunks = make_chunks([node])
        self.assertEqual(len(chunks), 1)
        self.assertIn("General document text", chunks[0].text)

    def test_docling_chunks_keep_contextualized_text(self):
        node_id = uuid4()
        source_document = object()
        docling_chunk = object()

        class Chunker:
            def chunk(self, dl_doc):
                self.asserted_doc = dl_doc
                return [docling_chunk]

            def contextualize(self, chunk):
                return "Article 1\n\nLegal text"

        chunker = Chunker()
        chunks = chunking_service.make_docling_chunks(source_document, chunker, node_id)
        self.assertIs(chunker.asserted_doc, source_document)
        self.assertEqual(chunks[0].node_id, node_id)
        self.assertEqual(chunks[0].text, "Article 1\n\nLegal text")

    def test_docling_chunks_map_to_heading_node(self):
        node_id = uuid4()
        docling_chunk = SimpleNamespace(meta=SimpleNamespace(headings=["Overview", "Details"]))

        class Chunker:
            def chunk(self, dl_doc):
                return [docling_chunk]

            def contextualize(self, chunk):
                return "Details text"

        chunks = chunking_service.make_docling_chunks(
            object(), Chunker(), {("Overview", "Details"): node_id}
        )
        self.assertEqual(chunks[0].node_id, node_id)

    def test_chunker_uses_tokenizer_and_budget_from_settings(self):
        modules = {
            "docling": types.ModuleType("docling"),
            "docling.chunking": types.ModuleType("docling.chunking"),
            "docling_core": types.ModuleType("docling_core"),
            "docling_core.transforms": types.ModuleType("docling_core.transforms"),
            "docling_core.transforms.chunker": types.ModuleType("docling_core.transforms.chunker"),
            "docling_core.transforms.chunker.tokenizer": types.ModuleType(
                "docling_core.transforms.chunker.tokenizer"
            ),
            "docling_core.transforms.chunker.tokenizer.huggingface": types.ModuleType(
                "docling_core.transforms.chunker.tokenizer.huggingface"
            ),
            "transformers": types.ModuleType("transformers"),
        }
        observed = {}

        class FakeHuggingFaceTokenizer:
            def __init__(self, tokenizer, max_tokens):
                observed["tokenizer"] = tokenizer
                observed["max_tokens"] = max_tokens

        class FakeHybridChunker:
            def __init__(self, tokenizer):
                observed["wrapped_tokenizer"] = tokenizer

        class FakeAutoTokenizer:
            @staticmethod
            def from_pretrained(model_name):
                observed["model_name"] = model_name
                return "loaded-tokenizer"

        modules["docling.chunking"].HybridChunker = FakeHybridChunker
        modules[
            "docling_core.transforms.chunker.tokenizer.huggingface"
        ].HuggingFaceTokenizer = FakeHuggingFaceTokenizer
        modules["transformers"].AutoTokenizer = FakeAutoTokenizer

        with (
            patch.dict(sys.modules, modules),
            patch.object(
                chunking_service,
                "get_settings",
                return_value=SimpleNamespace(EMBEDDING_CHUNK_MAX_TOKENS=384),
            ),
            patch.object(
                chunking_service,
                "embedding_tokenizer_model_name",
                return_value="Qwen/Qwen3-Embedding-0.6B",
            ),
            patch.object(chunking_service, "HybridChunker", FakeHybridChunker),
            patch.object(chunking_service, "HuggingFaceTokenizer", FakeHuggingFaceTokenizer),
            patch.object(chunking_service, "AutoTokenizer", FakeAutoTokenizer),
        ):
            chunking_service.create_docling_chunker()

        self.assertEqual(observed["model_name"], "Qwen/Qwen3-Embedding-0.6B")
        self.assertEqual(observed["max_tokens"], 384)
        self.assertEqual(observed["tokenizer"], "loaded-tokenizer")

    def test_tokenizer_setting_tracks_selected_embedding_provider(self):
        configured = SimpleNamespace(
            EMBEDDING_PROVIDER="ollama",
            OLLAMA_EMBEDDING_TOKENIZER="Qwen/Qwen3-Embedding-0.6B",
            OPENROUTER_EMBEDDING_TOKENIZER="nvidia/Nemotron-3-Embed-1B-BF16",
        )
        with (
            patch.object(embeddings_service, "get_settings", return_value=configured),
            patch.object(embeddings_service, "embedding_provider", return_value="ollama"),
        ):
            self.assertEqual(
                embeddings_service.embedding_tokenizer_model_name(),
                "Qwen/Qwen3-Embedding-0.6B",
            )
        with (
            patch.object(embeddings_service, "get_settings", return_value=configured),
            patch.object(embeddings_service, "embedding_provider", return_value="openrouter"),
        ):
            self.assertEqual(
                embeddings_service.embedding_tokenizer_model_name(),
                "nvidia/Nemotron-3-Embed-1B-BF16",
            )


if __name__ == "__main__":
    unittest.main()
