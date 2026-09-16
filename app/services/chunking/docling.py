"""Docling document loading and tokenizer-backed chunker setup."""


from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DoclingDocument
from transformers import AutoTokenizer


from app.config import get_settings
from app.services.embeddings import embedding_tokenizer_model_name
from app.settings import Settings


def load_docling_document(path: str) -> DoclingDocument:
    if DoclingDocument is None:
        raise RuntimeError("Docling is required to load structured documents.")

    return DoclingDocument.load_from_json(path)


def create_docling_chunker(
    hybrid_chunker: AutoTokenizer = HybridChunker,
    tokenizer_type: HuggingFaceTokenizer = HuggingFaceTokenizer,
    auto_tokenizer: AutoTokenizer = AutoTokenizer,
    settings_loader: Settings = get_settings,
    model_name_loader: str = embedding_tokenizer_model_name,
) -> HybridChunker:

    if any(dependency is None for dependency in (hybrid_chunker, tokenizer_type, auto_tokenizer)):
        raise RuntimeError("Docling and Transformers are required for structured chunking.")

    settings = settings_loader()
    model_name = model_name_loader()

    if not model_name:
        raise ValueError("An embedding tokenizer model must be configured.")

    if settings.EMBEDDING_CHUNK_MAX_TOKENS < 1:
        raise ValueError("EMBEDDING_CHUNK_MAX_TOKENS must be positive.")

    tokenizer = tokenizer_type(
        tokenizer=auto_tokenizer.from_pretrained(model_name),
        max_tokens=settings.EMBEDDING_CHUNK_MAX_TOKENS,
    )

    return hybrid_chunker(tokenizer=tokenizer)
