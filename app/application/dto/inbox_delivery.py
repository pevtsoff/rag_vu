from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class InboxDelivery:
    inbox_id: UUID
    consumer: str
