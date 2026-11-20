"""A text chunk produced by chunking, before it is stored."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ChunkDraft:
    node_id: UUID
    position: int
    text: str
