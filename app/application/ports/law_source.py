"""A source of legal documents that are already structured into nodes."""

from abc import ABC, abstractmethod

from app.application.dto.law_document import LawDocument


class LawSource(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> LawDocument: ...
