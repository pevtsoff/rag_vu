import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.adapters.outbound.storage.local_file_storage import LocalFileStorage
from app.application.errors import StorageError
from tests.unit.fakes.fake_ports import BytesStream


async def test_stage_writes_and_fingerprints_the_stream(tmp_path: Path) -> None:
    staged = await LocalFileStorage(tmp_path).stage(BytesStream(b"pdf data"), "../../evil.pdf", "")
    assert Path(staged.path).read_bytes() == b"pdf data"
    assert Path(staged.path).parent == tmp_path / ".incoming"
    assert (staged.file_name, staged.mime_type, staged.size) == (
        "evil.pdf",
        "application/octet-stream",
        8,
    )
    assert staged.sha256 == hashlib.sha256(b"pdf data").hexdigest()


async def test_promote_moves_the_file_and_is_idempotent(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    staged = await storage.stage(BytesStream(b"data"), "law.pdf", "application/pdf")
    document_id = uuid4()

    first = await storage.promote(staged.path, document_id, "law.pdf")
    again = await storage.promote(staged.path, document_id, "law.pdf")  # retried job
    in_place = await storage.promote(first.path, document_id, "law.pdf")  # duplicate upload

    assert first == again == in_place
    assert first.path == str(tmp_path / str(document_id) / "law.pdf")
    assert not Path(staged.path).exists()


async def test_promote_fails_when_nothing_was_staged(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        await LocalFileStorage(tmp_path).promote(str(tmp_path / "missing"), uuid4(), "x.pdf")


async def test_failed_stream_leaves_no_partial_file(tmp_path: Path) -> None:
    class BrokenStream:
        async def read(self, size: int = -1) -> bytes:
            raise OSError("connection reset")

    with pytest.raises(StorageError, match="connection reset"):
        await LocalFileStorage(tmp_path).stage(BrokenStream(), "x.pdf", "application/pdf")
    assert list((tmp_path / ".incoming").iterdir()) == []
