from dataclasses import dataclass, field


@dataclass
class RankedCandidate:
    text: str
    node_ids: list[str]
    score: float = 0.0
    sources: set[str] = field(default_factory=set)
