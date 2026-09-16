"""Provide lightweight optional dependency stubs for test collection."""

import importlib.util
import sys
import types


def _module(name: str, package: bool = False) -> types.ModuleType:
    module = types.ModuleType(name)
    if package:
        module.__path__ = []
    sys.modules[name] = module
    return module


def _stub_docling() -> None:
    docling = _module("docling", package=True)
    _module("docling.chunking").HybridChunker = object
    _module("docling.datamodel", package=True)
    _module("docling.datamodel.base_models").InputFormat = types.SimpleNamespace(PDF="pdf")
    options = _module("docling.datamodel.pipeline_options")
    options.PdfPipelineOptions = type("PdfPipelineOptions", (), {})
    options.TesseractCliOcrOptions = type(
        "TesseractCliOcrOptions",
        (),
        {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)},
    )
    converter = _module("docling.document_converter")
    converter.DocumentConverter = object
    converter.PdfFormatOption = lambda **kwargs: types.SimpleNamespace(**kwargs)
    core = _module("docling_core", package=True)
    _module("docling_core.transforms", package=True)
    _module("docling_core.transforms.chunker", package=True)
    _module("docling_core.transforms.chunker.tokenizer", package=True)
    _module("docling_core.transforms.chunker.tokenizer.huggingface").HuggingFaceTokenizer = object
    _module("docling_core.types", package=True)
    doc_types = _module("docling_core.types.doc")
    doc_types.DoclingDocument = None
    doc_types.ImageRefMode = types.SimpleNamespace(PLACEHOLDER="placeholder")
    _module("transformers").AutoTokenizer = None
    docling.__path__ = []
    core.__path__ = []


if importlib.util.find_spec("docling") is None:
    _stub_docling()
