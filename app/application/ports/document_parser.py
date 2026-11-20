"""Conversion of a stored file into structural nodes."""

from abc import ABC, abstractmethod

from app.application.dto.parsed_document import ParsedDocument


class DocumentParser(ABC):
    @abstractmethod
    async def parse(self, file_path: str, fallback_title: str) -> ParsedDocument: ...
