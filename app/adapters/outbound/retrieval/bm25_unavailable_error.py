class Bm25UnavailableError(RuntimeError):
    """pg_textsearch or the nodes BM25 index is missing."""
