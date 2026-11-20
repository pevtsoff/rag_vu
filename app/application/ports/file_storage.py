"""Storage of uploaded files."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.staged_file import StagedFile
from app.application.dto.stored_file import StoredFile
from app.application.ports.byte_stream import ByteStream


class FileStorage(ABC):
    @abstractmethod
    async def stage(self, stream: ByteStream, file_name: str, mime_type: str) -> StagedFile:
        """Write an incoming stream to a temporary location and fingerprint it."""

    @abstractmethod
    async def promote(self, staged_path: str, document_id: UUID, file_name: str) -> StoredFile:
        """Move a staged file to its permanent location; tolerate an earlier move."""

    @abstractmethod
    async def discard(self, path: str) -> None: ...
