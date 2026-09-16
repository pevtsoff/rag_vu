"""Tests for the HTML endpoint that serves legal article nodes."""

import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.api.v1.nodes import read_node_html
from app.models.db.node import Node


class FakeResult:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


class FakeSession:
    def __init__(self, row):
        self.row = row

    async def execute(self, statement):
        return FakeResult(self.row)


class TestNodeHtmlEndpoint(unittest.IsolatedAsyncioTestCase):
    def make_row(self, node_type):
        node = Node(
            id=uuid4(),
            document_id=uuid4(),
            title="Статья 10 <Право>",
            breadcrumbs=["Федеральный закон", "Статья 10"],
            text="Пункт <script>alert('x')</script>\nВторая строка.",
            node_type=node_type,
        )
        return node, "Закон <пример>"

    async def test_renders_retrievable_legal_node_types_as_html(self):
        for node_type in ("article", "article_part", "section", "preamble", "header"):
            with self.subTest(node_type=node_type):
                node, document_title = self.make_row(node_type)
                response = await read_node_html(
                    node.id,
                    session=FakeSession((node, document_title)),
                )
                body = response.body.decode("utf-8")

                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.media_type)
                self.assertIn('<html lang="ru">', body)
                self.assertIn(f'data-node-type="{node_type}"', body)
                self.assertIn("Статья 10 &lt;Право&gt;", body)
                self.assertIn("Закон &lt;пример&gt;", body)
                self.assertIn("&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;", body)
                self.assertNotIn("<script>", body)
                self.assertIn("Федеральный закон › Статья 10", body)

    async def test_returns_404_for_missing_node(self):
        with self.assertRaises(HTTPException) as raised:
            await read_node_html(uuid4(), session=FakeSession(None))

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Node not found")

    async def test_returns_404_for_node_that_is_not_renderable(self):
        node, document_title = self.make_row("document")
        with self.assertRaises(HTTPException) as raised:
            await read_node_html(
                node.id,
                session=FakeSession((node, document_title)),
            )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Node not found")


if __name__ == "__main__":
    unittest.main()
