from dataclasses import dataclass


@dataclass(frozen=True)
class VersioningInput:
    """The embedded chunks of a document, in document order."""

    texts: list[str]
    vectors: list[list[float]]
    dimensions: int | None
