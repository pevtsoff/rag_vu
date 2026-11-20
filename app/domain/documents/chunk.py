"""A stored chunk whose text is embedded for vector search."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Chunk:
    id: UUID
    node_id: UUID
    position: int
    text: str
