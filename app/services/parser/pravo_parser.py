"""Parser for Russian legal documents from pravo.gov.ru.

Extracts document content into nodes for RAG.

Legal hierarchy:

    Law
      -> Section <number> — <name>
        -> Article <number> — <name>
          -> Article part <number>

Example:

    Статья 52. Зачисление в запас

    1. Запас Вооруженных Сил...
    2. Гражданину...
    3. Гражданину...

becomes:

    ARTICLE
      path: s1.a52

    ARTICLE_PART
      path: s1.a52.p1

    ARTICLE_PART
      path: s1.a52.p2

    ARTICLE_PART
      path: s1.a52.p3
"""

import asyncio
import json
import re
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy_utils import Ltree

from app.db.db_enums.node_types import NodeTypes as LawNodeTypes
from app.models.db.document import Document
from app.models.db.node import Node
from app.models.db.pipeline import PipelineStatus

PARSER_DATABASE_URL = "postgresql+asyncpg://rag_vu_user:rag_vu_password@localhost:8432/rag_vu_db"


class LawDocumentParser:
    """Parser for Russian legal documents from pravo.gov.ru."""

    BASE_URL = "http://pravo.gov.ru"

    SECTION_RE = re.compile(
        r"^\s*РАЗДЕЛ\s+([IVXLCDM]+|\d+)\s*[\.\-:]?\s*(.*?)\s*$",
        re.IGNORECASE,
    )

    ARTICLE_RE = re.compile(
        r"^\s*СТАТЬЯ\s+(\d+(?:\.\d+)?)\s*[\.\-:]?\s*(.*?)\s*$",
        re.IGNORECASE,
    )

    # Examples:
    #   1. Запас Вооруженных Сил...
    #   2. Гражданину...
    PART_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")

    def __init__(self, url: str):
        # Trim accidental whitespace so URLs copied into a list still work.
        self.url = re.sub(r"\s+", "", url)
        self.soup = None
        self.title = ""
        self.articles = []
        self.body_text = ""
        self.metadata = {}
        self.nodes = []

    # ------------------------------------------------------------------
    # Fetch / cleanup
    # ------------------------------------------------------------------

    def fetch(self) -> bool:
        """Fetch the HTML document using the page's declared encoding."""
        try:
            resp = httpx.get(
                self.url,
                timeout=30.0,
                follow_redirects=True,
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            charset_match = re.search(
                r"charset\s*=\s*['\"]?([\w-]+)",
                content_type,
                re.IGNORECASE,
            )

            if charset_match:
                resp.encoding = charset_match.group(1)
            elif not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "windows-1251"

            self.soup = BeautifulSoup(
                resp.text,
                "html.parser",
            )

            return True

        except httpx.HTTPError as exc:
            print(f"Error fetching document: {exc}")
            return False

        except Exception as exc:
            print(f"Error fetching document: {exc}")
            return False

    def _remove_unwanted(self):
        """Remove elements that should not participate in parsing."""
        for element in self.soup(
            [
                "script",
                "style",
                "img",
                "input",
                "button",
                "select",
                "option",
                "noscript",
            ]
        ):
            element.decompose()

    # ------------------------------------------------------------------
    # Text / headings
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    @classmethod
    def _parse_section_heading(
        cls,
        line: str,
    ) -> tuple[str, str] | None:
        match = cls.SECTION_RE.match(cls._clean_text(line))

        if not match:
            return None

        number = match.group(1)
        name = cls._clean_text(match.group(2))

        return number, name

    @classmethod
    def _parse_article_heading(
        cls,
        line: str,
    ) -> tuple[str, str] | None:
        match = cls.ARTICLE_RE.match(cls._clean_text(line))

        if not match:
            return None

        number = match.group(1)
        name = cls._clean_text(match.group(2))

        return number, name

    @classmethod
    def _parse_article_part(
        cls,
        line: str,
    ) -> tuple[str, str] | None:
        match = cls.PART_RE.match(cls._clean_text(line))

        if not match:
            return None

        number = match.group(1)
        text = cls._clean_text(match.group(2))

        return number, text

    @staticmethod
    def _breadcrumb_item(
        prefix: str,
        number: str,
        name: str,
    ) -> str:
        if name:
            return f"{prefix} {number} — {name}"

        return f"{prefix} {number}"

    # ------------------------------------------------------------------
    # Document metadata
    # ------------------------------------------------------------------

    def _extract_title(self):
        """Extract the document title."""
        for selector in (
            "div.h1",
            "h1",
            ".doc_title",
            "title",
        ):
            elem = self.soup.select_one(selector)

            if elem:
                value = self._clean_text(elem.get_text(" ", strip=True))

                if value:
                    self.title = value
                    break

        if not self.title:
            number_match = re.search(
                r"(\d{1,5}-\w\d+)",
                self.url or "",
                re.IGNORECASE,
            )

            if number_match:
                self.title = number_match.group(1)

    def _extract_metadata(self):
        """Extract document metadata."""
        text = self.soup.get_text(" ", strip=True)

        number_match = re.search(
            r"(?:№\s*)?(\d{1,5}-[А-ЯA-ZЁ]\w*)",
            text,
            re.IGNORECASE,
        )

        if number_match:
            self.metadata["number"] = number_match.group(1)

        dates = re.findall(
            r"\d{1,2}\.\d{1,2}\.\d{4}",
            text,
        )

        if dates:
            self.metadata["dates"] = dates[:3]

        for document_type in (
            "Федеральный закон",
            "Закон",
            "Указ",
            "Постановление",
            "Распоряжение",
        ):
            if document_type in text:
                self.metadata["type"] = document_type
                break

    # ------------------------------------------------------------------
    # Article references
    # ------------------------------------------------------------------

    def _extract_article_references(self) -> list:
        """Extract actual article headings."""
        references = []
        seen = set()

        for line in self.body_text.splitlines():
            parsed = self._parse_article_heading(line)

            if not parsed:
                continue

            number, name = parsed

            if number in seen:
                continue

            seen.add(number)

            references.append(
                {
                    "number": number,
                    "name": name,
                    "type": "article",
                }
            )

        return references

    # ------------------------------------------------------------------
    # Document-level splitting
    # ------------------------------------------------------------------

    def _split_into_sections(
        self,
        text: str,
    ) -> list[str]:
        """Split document only at section/article headings.

        Numbered article parts are NOT split here.
        They are split later by _split_article_parts().
        """
        lines = text.splitlines()
        starts = []

        for index, line in enumerate(lines):
            stripped = line.strip()

            if self._parse_section_heading(stripped):
                starts.append(index)

            elif self._parse_article_heading(stripped):
                starts.append(index)

        if not starts:
            return [text] if text.strip() else []

        # Preserve preamble/header before first legal heading.
        if starts[0] > 0:
            prefix = "\n".join(lines[: starts[0]]).strip()

            if prefix:
                starts.insert(0, 0)

        sections = []

        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(lines)

            chunk = "\n".join(lines[start:end]).strip()

            if len(chunk) > 10:
                sections.append(chunk)

        return sections

    # ------------------------------------------------------------------
    # Article splitting
    # ------------------------------------------------------------------

    def _article_name_from_chunk(
        self,
        article_text: str,
    ) -> tuple[str | None, str]:
        """Extract article number and name."""
        lines = [line.strip() for line in article_text.splitlines() if line.strip()]

        if not lines:
            return None, ""

        parsed = self._parse_article_heading(lines[0])

        if not parsed:
            return None, ""

        number, name = parsed

        # Some pravo.gov.ru documents use:
        #
        # Статья 1.
        # Основные понятия
        #
        if not name and len(lines) > 1:
            candidate = lines[1]

            if (
                not self._parse_section_heading(candidate)
                and not self._parse_article_heading(candidate)
                and not self.PART_RE.match(candidate)
                and len(candidate) < 300
            ):
                name = self._clean_text(candidate)

        return number, name

    def _split_article_parts(
        self,
        article_text: str,
    ) -> list[dict]:
        """Split an article into numbered article parts.

        Returns dictionaries like:

            {
                "number": "1",
                "content": "1. Запас Вооруженных Сил..."
            }

        The article heading itself is NOT returned as a part.
        """
        lines = article_text.splitlines()

        part_starts = []

        for index, line in enumerate(lines):
            if self._parse_article_part(line.strip()):
                part_starts.append(index)

        # Article has no numbered parts.
        if not part_starts:
            return []

        parts = []

        for index, start in enumerate(part_starts):
            end = part_starts[index + 1] if index + 1 < len(part_starts) else len(lines)

            content = "\n".join(lines[start:end]).strip()

            if not content:
                continue

            parsed = self._parse_article_part(lines[start].strip())

            if not parsed:
                continue

            number, _ = parsed

            parts.append(
                {
                    "number": number,
                    "content": content,
                }
            )

        return parts

    # ------------------------------------------------------------------
    # Node types
    # ------------------------------------------------------------------

    def _determine_node_type(
        self,
        section_text: str,
    ) -> str:
        """Determine node type from the first meaningful line."""
        lines = [line.strip() for line in section_text.splitlines() if line.strip()]

        first_line = lines[0] if lines else ""

        if re.match(
            r"^\s*РОССИЙСКАЯ\s+ФЕДЕРАЦИЯ",
            first_line,
            re.IGNORECASE,
        ):
            return LawNodeTypes.PREAMBLE.value

        if re.match(
            r"^\s*ФЕДЕРАЛЬНЫЙ\s+ЗАКОН",
            first_line,
            re.IGNORECASE,
        ):
            return LawNodeTypes.PREAMBLE.value

        if self._parse_section_heading(first_line):
            return LawNodeTypes.SECTION.value

        if self._parse_article_heading(first_line):
            return LawNodeTypes.ARTICLE.value

        return LawNodeTypes.HEADER.value

    # ------------------------------------------------------------------
    # Breadcrumbs
    # ------------------------------------------------------------------

    def _build_breadcrumb(
        self,
        node_type: str,
        section_number: str | None,
        section_name: str,
        article_number: str | None,
        article_name: str,
        part_number: str | None = None,
    ) -> list[str]:
        """Build the complete legal hierarchy."""
        if node_type in (
            LawNodeTypes.PREAMBLE.value,
            LawNodeTypes.HEADER.value,
        ):
            return [self.title] if self.title else []

        breadcrumb = []

        if self.title:
            breadcrumb.append(self.title)

        if section_number:
            breadcrumb.append(
                self._breadcrumb_item(
                    "Раздел",
                    section_number,
                    section_name,
                )
            )

        if article_number:
            breadcrumb.append(
                self._breadcrumb_item(
                    "Статья",
                    article_number,
                    article_name,
                )
            )

        if part_number and node_type == LawNodeTypes.ARTICLE_PART.value:
            breadcrumb.append(f"Пункт {part_number}")

        return breadcrumb

    # ------------------------------------------------------------------
    # ltree
    # ------------------------------------------------------------------

    @staticmethod
    def _ltree_label(
        prefix: str,
        number: str,
    ) -> str:
        """Return a valid non-numeric ltree label."""
        safe_number = re.sub(
            r"[^A-Za-z0-9_]",
            "_",
            str(number),
        )

        return f"{prefix}{safe_number}"

    def _build_ltree_path(
        self,
        section_number: str | None,
        article_number: str | None,
        part_number: str | None = None,
        fallback_index: int | None = None,
    ) -> str:
        """Build hierarchical ltree path."""
        path_parts = []

        if section_number:
            path_parts.append(
                self._ltree_label(
                    "s",
                    section_number,
                )
            )

        if article_number:
            path_parts.append(
                self._ltree_label(
                    "a",
                    article_number,
                )
            )

        if part_number:
            path_parts.append(
                self._ltree_label(
                    "p",
                    part_number,
                )
            )

        if not path_parts:
            return f"n{fallback_index}" if fallback_index is not None else "n1"

        return ".".join(path_parts)

    # ------------------------------------------------------------------
    # Node factory
    # ------------------------------------------------------------------

    def _make_node(
        self,
        *,
        node_id: str,
        node_type: str,
        content: str,
        title: str,
        breadcrumb: list[str],
        path: str,
        section_number: str | None,
        section_name: str,
        article_number: str | None,
        article_name: str,
        part_number: str | None = None,
        index: int,
        total_nodes: int,
    ) -> dict:
        """Create a normalized node dictionary."""
        return {
            "id": node_id,
            "type": node_type,
            "content": content,
            "title": title,
            "breadcrumb": breadcrumb,
            "metadata": {
                "document_number": self.metadata.get(
                    "number",
                    "",
                ),
                "document_title": self.title,
                "section_number": section_number,
                "section_name": section_name,
                "article_number": article_number,
                "article_name": article_name,
                "article_part_number": part_number,
                "section_index": index,
                "total_sections": total_nodes,
                "source_url": self.url,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "path": path,
        }

    # ------------------------------------------------------------------
    # Main parser
    # ------------------------------------------------------------------

    def parse(self) -> dict:
        """Parse the full document and return structured data."""
        if not self.fetch():
            return {"error": "Failed to fetch document"}

        self._remove_unwanted()
        self._extract_title()
        self._extract_metadata()

        body_selectors = [
            ".docbody",
            "[id*='body']",
            ".main-content",
            "body",
        ]

        body_text = ""

        for selector in body_selectors:
            elem = self.soup.select_one(selector)

            if elem:
                body_text = elem.get_text(
                    separator="\n",
                    strip=True,
                )

                if len(body_text) > 200:
                    break

        if not body_text:
            body_text = self.soup.get_text(
                separator="\n",
                strip=True,
            )

        self.body_text = body_text
        self.articles = self._extract_article_references()

        chunks = self._split_into_sections(body_text)

        nodes = []

        current_section_number = None
        current_section_name = ""

        current_article_number = None
        current_article_name = ""

        node_index = 0

        for chunk in chunks:
            node_type = self._determine_node_type(chunk)

            lines = [line.strip() for line in chunk.splitlines() if line.strip()]

            first_line = lines[0] if lines else ""

            # ----------------------------------------------------------
            # SECTION
            # ----------------------------------------------------------

            if node_type == LawNodeTypes.SECTION.value:
                parsed_section = self._parse_section_heading(first_line)

                if not parsed_section:
                    continue

                (
                    current_section_number,
                    current_section_name,
                ) = parsed_section

                current_article_number = None
                current_article_name = ""

                breadcrumb = self._build_breadcrumb(
                    node_type=node_type,
                    section_number=current_section_number,
                    section_name=current_section_name,
                    article_number=None,
                    article_name="",
                )

                path = self._build_ltree_path(
                    section_number=current_section_number,
                    article_number=None,
                )

                node_index += 1

                nodes.append(
                    self._make_node(
                        node_id=f"node_{node_index}",
                        node_type=node_type,
                        content=chunk,
                        title=(breadcrumb[-1] if breadcrumb else "Раздел"),
                        breadcrumb=breadcrumb,
                        path=path,
                        section_number=current_section_number,
                        section_name=current_section_name,
                        article_number=None,
                        article_name="",
                        index=node_index,
                        total_nodes=0,
                    )
                )

                continue

            # ----------------------------------------------------------
            # ARTICLE
            # ----------------------------------------------------------

            if node_type == LawNodeTypes.ARTICLE.value:
                (
                    article_number,
                    article_name,
                ) = self._article_name_from_chunk(chunk)

                if not article_number:
                    continue

                current_article_number = article_number
                current_article_name = article_name

                breadcrumb = self._build_breadcrumb(
                    node_type=node_type,
                    section_number=current_section_number,
                    section_name=current_section_name,
                    article_number=current_article_number,
                    article_name=current_article_name,
                )

                article_path = self._build_ltree_path(
                    section_number=current_section_number,
                    article_number=current_article_number,
                )

                # ------------------------------------------------------
                # ARTICLE NODE
                #
                # Keep the complete article on its ARTICLE node. Numbered
                # paragraphs are also stored as ARTICLE_PART child nodes for
                # precise retrieval and chunking.
                # ------------------------------------------------------

                node_index += 1

                nodes.append(
                    self._make_node(
                        node_id=f"node_{node_index}",
                        node_type=LawNodeTypes.ARTICLE.value,
                        content=chunk,
                        title=(breadcrumb[-1] if breadcrumb else "Статья"),
                        breadcrumb=breadcrumb,
                        path=article_path,
                        section_number=current_section_number,
                        section_name=current_section_name,
                        article_number=current_article_number,
                        article_name=current_article_name,
                        index=node_index,
                        total_nodes=0,
                    )
                )

                # ------------------------------------------------------
                # ARTICLE PARTS
                # ------------------------------------------------------

                article_parts = self._split_article_parts(chunk)

                for part in article_parts:
                    part_number = part["number"]
                    part_content = part["content"]

                    part_breadcrumb = self._build_breadcrumb(
                        node_type=(LawNodeTypes.ARTICLE_PART.value),
                        section_number=current_section_number,
                        section_name=current_section_name,
                        article_number=current_article_number,
                        article_name=current_article_name,
                        part_number=part_number,
                    )

                    part_path = self._build_ltree_path(
                        section_number=current_section_number,
                        article_number=current_article_number,
                        part_number=part_number,
                    )

                    node_index += 1

                    nodes.append(
                        self._make_node(
                            node_id=f"node_{node_index}",
                            node_type=(LawNodeTypes.ARTICLE_PART.value),
                            content=part_content,
                            title=(f"Пункт {part_number}"),
                            breadcrumb=part_breadcrumb,
                            path=part_path,
                            section_number=current_section_number,
                            section_name=current_section_name,
                            article_number=current_article_number,
                            article_name=current_article_name,
                            part_number=part_number,
                            index=node_index,
                            total_nodes=0,
                        )
                    )

                continue

            # ----------------------------------------------------------
            # PREAMBLE / HEADER
            # ----------------------------------------------------------

            breadcrumb = self._build_breadcrumb(
                node_type=node_type,
                section_number=None,
                section_name="",
                article_number=None,
                article_name="",
            )

            if node_type == LawNodeTypes.PREAMBLE.value:
                title = "Преамбула"

            elif node_type == LawNodeTypes.HEADER.value:
                title = self.title or (lines[0] if lines else "Header")

            else:
                title = lines[0] if lines else "Node"

            node_index += 1

            nodes.append(
                self._make_node(
                    node_id=f"node_{node_index}",
                    node_type=node_type,
                    content=(
                        self.title
                        if (node_type == LawNodeTypes.HEADER.value and self.title)
                        else chunk[:3000]
                    ),
                    title=title,
                    breadcrumb=breadcrumb,
                    path=f"n{node_index}",
                    section_number=None,
                    section_name="",
                    article_number=None,
                    article_name="",
                    index=node_index,
                    total_nodes=0,
                )
            )

        # Fill total node count after construction.
        for node in nodes:
            node["metadata"]["total_sections"] = len(nodes)

        self.nodes = nodes

        return {
            "title": self.title,
            "metadata": self.metadata,
            "articles": self.articles,
            "nodes": nodes,
            "body_text": body_text,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_nodes(self, output_path: str):
        """Save parsed nodes as JSON."""
        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self.nodes,
                file,
                ensure_ascii=False,
                indent=2,
            )


def parse_law_document(
    url: str,
    output_path: str = None,
) -> dict:
    """Convenience function to parse a law document."""
    parser = LawDocumentParser(url)
    result = parser.parse()

    if output_path:
        parser.save_nodes(output_path)

    return result


async def save_to_database(url: str) -> dict:
    """Save parsed document and nodes to the database."""
    engine = create_async_engine(
        PARSER_DATABASE_URL,
        echo=False,
    )

    async_session_local = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    parser = LawDocumentParser(url)
    result = parser.parse()

    if "error" in result:
        return {"error": result["error"]}

    document_title = parser.title or "Law Document"

    doc = Document(
        file_name=document_title,
        file_path=url,
        size=(len(parser.body_text) if parser.body_text else 0),
        status=PipelineStatus.IN_PROGRESS,
        mime_type="text/plain",
        metadata=parser.metadata,
        version=1,
    )

    async with async_session_local() as session:
        try:
            session.add(doc)
            await session.commit()
            await session.refresh(doc)

            for node_data in parser.nodes:
                breadcrumb = node_data.get(
                    "breadcrumb",
                    [],
                )

                breadcrumb_json = breadcrumb if isinstance(breadcrumb, list) else []

                node = Node(
                    document_id=doc.id,
                    title=node_data.get(
                        "title",
                        f"Node {node_data.get('id', 'unknown')}",
                    ),
                    text=node_data.get(
                        "content",
                        "",
                    ),
                    node_type=node_data.get(
                        "type",
                        LawNodeTypes.HEADER.value,
                    ),
                    breadcrumbs=breadcrumb_json,
                    path=Ltree(
                        node_data.get(
                            "path",
                            "",
                        )
                    ),
                )

                session.add(node)

            await session.commit()

            return {
                "document_id": str(doc.id),
                "nodes_created": len(parser.nodes),
                "message": ("Document and nodes saved successfully"),
            }

        except Exception as exc:
            await session.rollback()

            print(f"Error saving to database: {exc}")

            return {"error": str(exc)}


async def main():
    """Parse and save each configured Rosguard document."""
    test_urls = (
        "https://rosguard.gov.ru/document/article/federalnyj-zakon-ot-28-marta-1998-g--53fz",
        "https://rosguard.gov.ru/document/article/federalnyj-zakon-ot-3-dekabrya-2012-g--230fz",
        "https: // rosguard.gov.ru / document / article / federalnyj-zakon-ot-7-maya-2013-g--79fz",
    )

    results = []

    for test_url in test_urls:
        parser = LawDocumentParser(test_url)
        result = parser.parse()

        if "error" in result:
            print(f"Error parsing {parser.url}: {result['error']}")
            results.append({"url": parser.url, "error": result["error"]})
            continue

        print(f"Parsed {parser.url}: {len(result['nodes'])} nodes")
        for node in result["nodes"]:
            print(node["type"], node["path"], node["breadcrumb"])

        save_result = await save_to_database(parser.url)
        if "error" in save_result:
            print(f"Error saving {parser.url}: {save_result['error']}")
            results.append({"url": parser.url, "error": save_result["error"]})
            continue

        print(f"Saved document ID: {save_result['document_id']}")
        print(f"Saved nodes: {save_result['nodes_created']}")
        results.append({"url": parser.url, **result, "save": save_result})

    return results


if __name__ == "__main__":
    asyncio.run(main())
