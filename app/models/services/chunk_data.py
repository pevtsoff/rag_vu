"""A text chunk associated with its source node."""

from dataclasses import dataclass


@dataclass
class ChunkData:
    node_id: object
    position: int
    text: str
