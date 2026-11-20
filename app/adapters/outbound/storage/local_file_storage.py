"""Uploads on the local file system: ``<root>/.incoming`` then ``<root>/<document_id>/``."""

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from app.application.dto.staged_file import StagedFile
from app.application.dto.stored_file import StoredFile
from app.application.errors import StorageError
from app.application.ports.byte_stream import ByteStream
from app.application.ports.file_storage import FileStorage

READ_SIZE = 1024 * 1024
DEFAULT_FILE_NAME = "upload"


class LocalFileStorage(FileStorage):
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    async def stage(self, stream: ByteStream, file_name: str, mime_type: str) -> StagedFile:
        incoming = self._root / ".incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        path = incoming / f"{uuid4()}.upload"
        try:
            size, sha256 = await _write_stream(stream, path)
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise StorageError(f"{type(exc).__name__}: {exc}") from exc
        return StagedFile(
            path=str(path),
            file_name=safe_file_name(file_name),
            mime_type=mime_type or "application/octet-stream",
            size=size,
            sha256=sha256,
        )

    async def promote(self, staged_path: str, document_id: UUID, file_name: str) -> StoredFile:
        source = Path(staged_path)
        target = self._root / str(document_id) / safe_file_name(file_name)
        await asyncio.to_thread(_move, source, target)
        size, sha256 = await asyncio.to_thread(_fingerprint, target)
        return StoredFile(path=str(target), size=size, sha256=sha256)

    async def discard(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)


def safe_file_name(file_name: str | None) -> str:
    """Drop any directory part a client sent with the name."""
    return Path(file_name or DEFAULT_FILE_NAME).name or DEFAULT_FILE_NAME


async def _write_stream(stream: ByteStream, path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("wb") as output:
        while chunk := await stream.read(READ_SIZE):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _move(source: Path, target: Path) -> None:
    """Idempotent move: a retry after a completed move finds the target in place."""
    if source.resolve() == target.resolve() and target.is_file():
        return
    if not source.is_file():
        if target.is_file():
            return
        raise StorageError(f"Staged file does not exist: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)


def _fingerprint(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(READ_SIZE):
            digest.update(chunk)
    return path.stat().st_size, digest.hexdigest()
