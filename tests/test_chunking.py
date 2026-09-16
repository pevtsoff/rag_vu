"""Tests for legal text chunk construction and database writes."""

import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.services.chunking import (
    ChunkData,
    build_chunk_text,
    load_nodes,
    make_chunks,
    normalize_text,
    save_chunks,
    split_long_part,
)


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class FakeSession:
    def __init__(self, values=()):
        self.values = values
        self.added = []
        self.committed = False
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return ScalarResult(self.values)

    def add_all(self, values):
        self.added.extend(values)

    async def commit(self):
        self.committed = True


class TestChunking(unittest.IsolatedAsyncioTestCase):
    def test_normalize_text_preserves_paragraph_boundaries(self):
        self.assertEqual(
            normalize_text(" First   paragraph.\r\n\r\n  Second\tparagraph. "),
            "First paragraph.\n\nSecond paragraph.",
        )

    def test_split_long_part_preserves_short_text_and_splits_long_text(self):
        short = "1. Short legal rule."
        self.assertEqual(split_long_part(short), [short])

        long_text = " ".join("Слово." for _ in range(240))
        chunks = split_long_part(long_text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1400 for chunk in chunks))
        self.assertEqual(" ".join(chunks), long_text)

    def test_chunk_text_includes_breadcrumb_hierarchy(self):
        node = SimpleNamespace(breadcrumbs=["Закон", "Статья 1"])
        self.assertEqual(
            build_chunk_text(node, "  Правило.  "),
            "Закон\nСтатья 1\n\nПравило.",
        )

    def test_make_chunks_skips_empty_nodes_and_assigns_positions(self):
        node_id = uuid4()
        nodes = [
            SimpleNamespace(
                id=node_id,
                text="Короткий текст.",
                breadcrumbs=["Статья 1"],
            ),
            SimpleNamespace(id=uuid4(), text="  ", breadcrumbs=[]),
        ]

        chunks = make_chunks(nodes)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].node_id, node_id)
        self.assertEqual(chunks[0].position, 0)
        self.assertIn("Статья 1", chunks[0].text)

    async def test_load_nodes_prefers_parts_and_keeps_unpartitioned_articles(self):
        document_id = uuid4()
        nodes = [
            SimpleNamespace(node_type="article", path="s1.a1"),
            SimpleNamespace(node_type="article_part", path="s1.a1.p1"),
            SimpleNamespace(node_type="article", path="s1.a2"),
        ]
        session = FakeSession(nodes)

        selected = await load_nodes(session, str(document_id))

        self.assertEqual(
            [(node.node_type, node.path) for node in selected],
            [("article_part", "s1.a1.p1"), ("article", "s1.a2")],
        )

    async def test_save_chunks_replaces_rows_and_commits(self):
        session = FakeSession()
        chunks = [ChunkData(node_id=uuid4(), position=0, text="Text")]

        await save_chunks(session, chunks, [[0.1, 0.2]], "embedding_small")

        self.assertEqual(len(session.statements), 1)
        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.added[0].embedding_small, [0.1, 0.2])
        self.assertTrue(session.committed)

    async def test_save_chunks_rejects_mismatched_embeddings(self):
        with self.assertRaisesRegex(ValueError, "chunks/embeddings mismatch"):
            await save_chunks(
                FakeSession(),
                [ChunkData(node_id=uuid4(), position=0, text="Text")],
                [],
                "embedding_small",
            )


if __name__ == "__main__":
    unittest.main()
