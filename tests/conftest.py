"""Stub optional heavy dependencies (Docling, Transformers) when they are not installed.

Adapters import them at module scope; unit tests replace the parts they exercise.
"""

import importlib.util
import sys
import types


def _module(name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = []
    module.__dict__.update(attributes)
    sys.modules[name] = module
    return module


class _Stub:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    @classmethod
    def load_from_json(cls, path: str) -> "_Stub":
        return cls(path=path)


def _stub_docling() -> None:
    _module("docling")
    _module("docling.chunking", HybridChunker=_Stub)
    _module("docling.datamodel")
    _module("docling.datamodel.base_models", InputFormat=types.SimpleNamespace(PDF="pdf"))
    _module(
        "docling.datamodel.pipeline_options",
        HeadingHierarchyOptions=_Stub,
        PdfPipelineOptions=_Stub,
        TesseractCliOcrOptions=_Stub,
    )
    _module("docling.document_converter", DocumentConverter=_Stub, PdfFormatOption=_Stub)
    _module("docling_core")
    _module("docling_core.transforms")
    _module("docling_core.transforms.chunker")
    _module("docling_core.transforms.chunker.tokenizer")
    _module("docling_core.transforms.chunker.tokenizer.huggingface", HuggingFaceTokenizer=_Stub)
    _module("docling_core.types")
    _module(
        "docling_core.types.doc",
        DoclingDocument=_Stub,
        ImageRefMode=types.SimpleNamespace(PLACEHOLDER="placeholder"),
    )


if importlib.util.find_spec("docling") is None:
    _stub_docling()
if importlib.util.find_spec("transformers") is None:
    _module("transformers", AutoTokenizer=_Stub)
