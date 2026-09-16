"""Exceptions raised by query services."""


class BM25SearchUnavailableError(RuntimeError):
    """Raised when pg_textsearch or its required BM25 index is unavailable."""
