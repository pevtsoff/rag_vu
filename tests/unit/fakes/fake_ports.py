"""Small fakes for the non-persistence ports."""

from uuid import UUID

from app.application.dto.job_route import JobRoute
from app.application.dto.parsed_document import ParsedDocument
from app.application.dto.staged_file import StagedFile
from app.application.dto.stored_file import StoredFile
from app.application.ports.byte_stream import ByteStream
from app.application.ports.chat_model import ChatModel
from app.application.ports.chunker import Chunker
from app.application.ports.document_parser import DocumentParser
from app.application.ports.embedder import Embedder
from app.application.ports.file_storage import FileStorage
from app.application.ports.job_dispatcher import JobDispatcher
from app.application.ports.reranker import Reranker
from app.application.ports.retriever import Retriever
from app.domain.documents.chunk_draft import ChunkDraft
from app.domain.documents.embedding_task import EmbeddingTask
from app.domain.documents.node import Node
from app.domain.documents.parsed_node import ParsedNode
from app.domain.retrieval.retrieved_match import RetrievedMatch


class BytesStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        size = len(self._data) if size < 0 else size
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


class FakeStorage(FileStorage):
    def __init__(self, sha256: str = "sha", size: int = 4) -> None:
        self.sha256, self.size = sha256, size
        self.discarded: list[str] = []
        self.promoted: list[tuple[str, UUID, str]] = []

    async def stage(self, stream: ByteStream, file_name: str, mime_type: str) -> StagedFile:
        await stream.read()
        return StagedFile(f"/incoming/{file_name}", file_name, mime_type, self.size, self.sha256)

    async def promote(self, staged_path: str, document_id: UUID, file_name: str) -> StoredFile:
        self.promoted.append((staged_path, document_id, file_name))
        return StoredFile(f"/documents/{document_id}/{file_name}", self.size, self.sha256)

    async def discard(self, path: str) -> None:
        self.discarded.append(path)


class FakeParser(DocumentParser):
    def __init__(
        self, nodes: list[ParsedNode] | None = None, error: Exception | None = None
    ) -> None:
        self.nodes = nodes or [
            ParsedNode("Doc", "First paragraph.", ["Doc"], "p000001", "preamble"),
            ParsedNode("Section", "Section text.", ["Doc", "Section"], "p000001.h1_s", "section"),
        ]
        self.error = error
        self.calls: list[str] = []

    async def parse(self, file_path: str, fallback_title: str) -> ParsedDocument:
        self.calls.append(file_path)
        if self.error:
            raise self.error
        return ParsedDocument("Doc", list(self.nodes), f"{file_path}.docling.json")


class FakeChunker(Chunker):
    def __init__(self) -> None:
        self.structure_paths: list[str | None] = []

    async def chunk(self, nodes: list[Node], structure_path: str | None) -> list[ChunkDraft]:
        self.structure_paths.append(structure_path)
        return [ChunkDraft(node.id, 0, node.text or "") for node in nodes]


class FakeEmbedder(Embedder):
    def __init__(self, dimensions: int = 768) -> None:
        self._dimensions = dimensions
        self.calls: list[tuple[list[str], EmbeddingTask]] = []

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str], task: EmbeddingTask) -> list[list[float]]:
        self.calls.append((texts, task))
        return [[float(len(text))] * self._dimensions for text in texts]


class RecordingDispatcher(JobDispatcher):
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.dispatched: list[tuple[JobRoute, UUID]] = []

    async def dispatch(self, route: JobRoute, inbox_id: UUID) -> None:
        if self.failing:
            raise ConnectionError("broker down")
        self.dispatched.append((route, inbox_id))


class FakeRetriever(Retriever):
    def __init__(self, matches: list[RetrievedMatch]) -> None:
        self.matches = matches
        self.calls: list[tuple[list[float], str]] = []

    async def retrieve(self, query_vector: list[float], query: str) -> list[RetrievedMatch]:
        self.calls.append((query_vector, query))
        return self.matches


class ReversingReranker(Reranker):
    async def rerank(self, query: str, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
        return list(reversed(matches))


class FakeChatModel(ChatModel):
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        return self.reply
