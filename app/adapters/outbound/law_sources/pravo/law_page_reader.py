"""Extracts title, metadata and body text from a law HTML page."""

import re

from bs4 import BeautifulSoup

from app.adapters.outbound.law_sources.pravo.law_text_patterns import clean_text

UNWANTED_TAGS = ["script", "style", "img", "input", "button", "select", "option", "noscript"]
TITLE_SELECTORS = ("div.h1", "h1", ".doc_title", "title")
BODY_SELECTORS = (".docbody", "[id*='body']", ".main-content", "body")
DOCUMENT_TYPES = ("Федеральный закон", "Закон", "Указ", "Постановление", "Распоряжение")
MIN_BODY_LENGTH = 200


class LawPageReader:
    def __init__(self, html: str, url: str) -> None:
        self._url = url
        self._soup = BeautifulSoup(html, "html.parser")
        for element in self._soup(UNWANTED_TAGS):
            element.decompose()

    def title(self) -> str:
        for selector in TITLE_SELECTORS:
            element = self._soup.select_one(selector)
            value = clean_text(element.get_text(" ", strip=True)) if element else ""
            if value:
                return value
        number = re.search(r"(\d{1,5}-\w\d+)", self._url, re.IGNORECASE)
        return number.group(1) if number else ""

    def metadata(self) -> dict:
        text = self._soup.get_text(" ", strip=True)
        metadata: dict = {}
        number = re.search(r"(?:№\s*)?(\d{1,5}-[А-ЯA-ZЁ]\w*)", text, re.IGNORECASE)
        if number:
            metadata["number"] = number.group(1)
        dates = re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}", text)
        if dates:
            metadata["dates"] = dates[:3]
        document_type = next((kind for kind in DOCUMENT_TYPES if kind in text), None)
        if document_type:
            metadata["type"] = document_type
        return metadata

    def body_text(self) -> str:
        """Prefer the first known body container whose text is long enough."""
        body = ""
        for selector in BODY_SELECTORS:
            element = self._soup.select_one(selector)
            if element:
                body = element.get_text(separator="\n", strip=True)
                if len(body) > MIN_BODY_LENGTH:
                    break
        return body or self._soup.get_text(separator="\n", strip=True)
