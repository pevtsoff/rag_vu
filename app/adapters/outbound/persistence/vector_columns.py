"""Which ``chunks`` column stores vectors of a given size."""

VECTOR_COLUMNS = {768: "embedding_small", 1536: "embedding_mid", 2048: "embedding_big"}


def vector_column_for(dimensions: int) -> str:
    try:
        return VECTOR_COLUMNS[dimensions]
    except KeyError as exc:
        supported = ", ".join(str(size) for size in VECTOR_COLUMNS)
        raise ValueError(f"Unsupported embedding size {dimensions}; use {supported}") from exc
