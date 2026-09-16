"""Deterministic tests for Russian legal document parsing."""

import json
import tempfile
import unittest
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup

from app.db.db_enums.node_types import NodeTypes
from app.services.parser.pravo_parser import LawDocumentParser

DOCUMENT_HTML = """
<html>
  <head><title>Federal law</title></head>
  <body>
    <script>this should be discarded</script>
    <div class="h1">Федеральный закон № 79-ФЗ</div>
    <div class="docbody">
      <div>ФЕДЕРАЛЬНЫЙ ЗАКОН</div>
      <div>от 7 мая 2013 г. № 79-ФЗ (07.05.2013)</div>
      <div>РАЗДЕЛ I. Общие положения</div>
      <div>Статья 1. Основные понятия</div>
      <div>1. Первое положение закона.</div>
      <div>2. Второе положение закона.</div>
      <div>Статья 2. Обязанности</div>
      <div>Гражданин обязан соблюдать закон.</div>
    </div>
  </body>
</html>
"""


class TestPravoParser(unittest.TestCase):
    def parse_fixture(self):
        parser = LawDocumentParser("https://example.test/law")
        parser.soup = BeautifulSoup(DOCUMENT_HTML, "html.parser")
        with patch.object(LawDocumentParser, "fetch", return_value=True):
            result = parser.parse()
        return parser, result

    def test_extracts_title_metadata_and_article_references(self):
        parser, result = self.parse_fixture()

        self.assertEqual(parser.title, "Федеральный закон № 79-ФЗ")
        self.assertEqual(parser.metadata["number"], "79-ФЗ")
        self.assertEqual(parser.metadata["type"], "Федеральный закон")
        self.assertIn("07.05.2013", parser.metadata["dates"])
        self.assertEqual([article["number"] for article in result["articles"]], ["1", "2"])

    def test_builds_section_article_and_part_nodes_with_paths(self):
        _, result = self.parse_fixture()
        nodes = result["nodes"]
        node_types = [node["type"] for node in nodes]

        self.assertIn(NodeTypes.SECTION.value, node_types)
        self.assertIn(NodeTypes.ARTICLE.value, node_types)
        self.assertIn(NodeTypes.ARTICLE_PART.value, node_types)
        self.assertTrue(any(node["path"] == "sI.a1.p1" for node in nodes))
        self.assertTrue(any(node["path"] == "sI.a1.p2" for node in nodes))
        self.assertTrue(any(node["path"] == "sI.a2" for node in nodes))
        self.assertTrue(all(node["metadata"]["total_sections"] == len(nodes) for node in nodes))

    def test_returns_document_shape_and_content(self):
        parser, result = self.parse_fixture()

        self.assertEqual(result["title"], parser.title)
        self.assertTrue(result["body_text"])
        self.assertNotIn("this should be discarded", result["body_text"])
        self.assertEqual(result["nodes"], parser.nodes)
        self.assertTrue(any("Первое положение" in node["content"] for node in parser.nodes))

    def test_handles_fetch_failure(self):
        parser = LawDocumentParser("https://example.test/missing")
        with patch.object(LawDocumentParser, "fetch", return_value=False):
            result = parser.parse()

        self.assertEqual(result, {"error": "Failed to fetch document"})

    def test_fetch_reads_response_with_declared_charset(self):
        parser = LawDocumentParser("https://example.test/law")
        response = httpx.Response(
            200,
            text=DOCUMENT_HTML,
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", parser.url),
        )
        with patch("app.services.parser.pravo_parser.httpx.get", return_value=response):
            fetched = parser.fetch()

        self.assertTrue(fetched)
        self.assertEqual(
            parser.soup.select_one(".h1").get_text(strip=True), "Федеральный закон № 79-ФЗ"
        )

    def test_saves_nodes_as_json(self):
        parser, _ = self.parse_fixture()
        with tempfile.TemporaryDirectory() as directory:
            output_path = f"{directory}/nodes.json"
            parser.save_nodes(output_path)
            with open(output_path, encoding="utf-8") as file:
                saved_nodes = json.load(file)

        self.assertEqual(saved_nodes, parser.nodes)


if __name__ == "__main__":
    unittest.main()
