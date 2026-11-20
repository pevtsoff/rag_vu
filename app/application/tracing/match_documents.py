"""Conversion of retrieved passages into traced documents."""

from collections.abc import Sequence

from app.application.tracing.traced_document import TracedDocument
from app.domain.retrieval.retrieved_match import RetrievedMatch

NODE_ID_SEPARATOR = ","


def match_documents(matches: Sequence[RetrievedMatch]) -> list[TracedDocument]:
    return [
        TracedDocument(
            id=NODE_ID_SEPARATOR.join(match.node_ids),
            content=match.text,
            score=match.score,
            metadata={"rank": rank, "node_count": len(match.node_ids)},
        )
        for rank, match in enumerate(matches, start=1)
    ]


def ranked_documents(source: str, ranked: Sequence[tuple[str, str]]) -> list[TracedDocument]:
    """Documents of one retrieval source, given as ``(key, text)`` best first."""
    return [
        TracedDocument(id=key, content=text, metadata={"rank": rank, "source": source})
        for rank, (key, text) in enumerate(ranked, start=1)
    ]
