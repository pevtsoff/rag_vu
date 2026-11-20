import httpx
import pytest

from app.adapters.outbound.law_sources.pravo.law_html_fetcher import fetch_law_html
from app.adapters.outbound.law_sources.pravo.pravo_law_source import PravoLawSource, normalize_url
from app.application.dto.law_document import LawDocument
from app.application.errors import LawImportError
from app.domain.documents.node_type import NodeType

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
      <div>Статья 2.</div>
      <div>Обязанности</div>
      <div>Гражданин обязан соблюдать закон.</div>
    </div>
  </body>
</html>
"""


def _law() -> LawDocument:
    return PravoLawSource(lambda url: DOCUMENT_HTML).read("https://example.test/law")


def test_extracts_title_metadata_and_article_references() -> None:
    law = _law()
    assert law.title == "Федеральный закон № 79-ФЗ"
    assert law.metadata["number"] == "79-ФЗ"
    assert law.metadata["type"] == "Федеральный закон"
    assert "07.05.2013" in law.metadata["dates"]
    assert [article["number"] for article in law.articles] == ["1", "2"]
    assert "this should be discarded" not in law.body_text


def test_builds_section_article_and_part_nodes_with_paths() -> None:
    nodes = {node.path: node for node in _law().nodes}
    assert nodes["sI"].node_type == NodeType.SECTION.value
    assert nodes["sI.a1"].node_type == NodeType.ARTICLE.value
    assert nodes["sI.a1.p1"].node_type == NodeType.ARTICLE_PART.value
    assert nodes["sI.a1.p1"].text == "1. Первое положение закона."
    assert nodes["sI.a1.p2"].breadcrumbs == [
        "Федеральный закон № 79-ФЗ",
        "Раздел I — Общие положения",
        "Статья 1 — Основные понятия",
        "Пункт 2",
    ]


def test_article_name_on_the_following_line_is_used() -> None:
    nodes = {node.path: node for node in _law().nodes}
    assert nodes["sI.a2"].title == "Статья 2 — Обязанности"


def test_a_page_without_legal_text_is_rejected() -> None:
    with pytest.raises(LawImportError):
        PravoLawSource(lambda url: "<html><body></body></html>").read("https://x")


def test_fetch_decodes_with_the_declared_charset() -> None:
    def get(url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            content=DOCUMENT_HTML.encode("windows-1251"),
            headers={"content-type": "text/html; charset=windows-1251"},
            request=httpx.Request("GET", url),
        )

    assert "Федеральный закон № 79-ФЗ" in fetch_law_html("https://x", get)


def test_fetch_failure_is_a_law_import_error() -> None:
    def get(url: str, **_: object) -> httpx.Response:
        return httpx.Response(404, request=httpx.Request("GET", url))

    with pytest.raises(LawImportError, match="Failed to fetch"):
        fetch_law_html("https://x", get)


def test_url_whitespace_is_removed() -> None:
    assert normalize_url("https: // rosguard.gov.ru / doc") == "https://rosguard.gov.ru/doc"
