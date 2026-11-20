"""A stored structural node of a document."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(kw_only=True)
class Node:
    document_id: UUID
    node_type: str
    title: str | None = None
    text: str | None = None
    breadcrumbs: list[str] | None = None
    path: str | None = None
    id: UUID = field(default_factory=uuid4)

    @property
    def has_text(self) -> bool:
        return bool((self.text or "").strip())
