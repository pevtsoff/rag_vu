"""An asynchronous readable byte stream, such as an HTTP upload."""

from typing import Protocol


class ByteStream(Protocol):
    async def read(self, size: int = -1) -> bytes: ...
