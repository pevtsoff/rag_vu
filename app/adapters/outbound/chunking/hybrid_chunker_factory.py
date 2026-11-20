"""Docling HybridChunker bound to the embedding model's tokenizer."""

from typing import Any

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer


def create_hybrid_chunker(
    model_name: str,
    max_tokens: int,
    hybrid_chunker: Any = HybridChunker,
    tokenizer_type: Any = HuggingFaceTokenizer,
    auto_tokenizer: Any = AutoTokenizer,
) -> Any:
    """Chunks are sized in tokens of the same model that embeds them."""
    if not model_name:
        raise ValueError("An embedding tokenizer model must be configured.")
    if max_tokens < 1:
        raise ValueError("EMBEDDING_CHUNK_MAX_TOKENS must be positive.")
    tokenizer = tokenizer_type(
        tokenizer=auto_tokenizer.from_pretrained(model_name), max_tokens=max_tokens
    )
    return hybrid_chunker(tokenizer=tokenizer)
