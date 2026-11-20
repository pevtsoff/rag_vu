"""A passage as it is recorded on a span."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TracedDocument:
    id: str
    content: str
    score: float | None = None
    metadata: dict[str, str | int | float] = field(default_factory=dict)
