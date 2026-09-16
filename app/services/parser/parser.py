import re
import unicodedata
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from app.models.services.parsed_node import ParsedNode


def _docling_label(item: Any) -> str:
    label = getattr(item, "label", "")
    return str(getattr(label, "value", label)).lower()


def _page_number(item: Any) -> int | None:
    provenance = getattr(item, "prov", None) or []
    numbers = [getattr(entry, "page_no", None) for entry in provenance]
    numbers = [number for number in numbers if isinstance(number, int) and number > 0]
    return min(numbers) if numbers else None


def _ltree_label(value: str, fallback: str) -> str:
    """Make a stable alphabetic ltree label from source text."""
    cyrillic = dict(
        zip(
            "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
            (
                "a",
                "b",
                "v",
                "g",
                "d",
                "e",
                "e",
                "zh",
                "z",
                "i",
                "i",
                "k",
                "l",
                "m",
                "n",
                "o",
                "p",
                "r",
                "s",
                "t",
                "u",
                "f",
                "kh",
                "ts",
                "ch",
                "sh",
                "shch",
                "",
                "y",
                "",
                "e",
                "yu",
                "ya",
            ),
        )
    )
    transliterated = "".join(cyrillic.get(char, char) for char in value.lower())
    normalized = (
        unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode().lower()
    )
    label = re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")
    if not label or not label[0].isalpha():
        label = f"{fallback}_{label}" if label else fallback
    return label[:200]


def build_nodes_from_docling(docling_document: Any, document_title: str) -> list[ParsedNode]:
    """Build searchable nodes from Docling's ordered items and heading levels."""
    nodes: list[ParsedNode] = []
    stack: list[dict[str, Any]] = []
    sibling_counts: dict[str, int] = {}
    preambles: dict[int | None, list[str]] = {}

    for item, _tree_level in docling_document.iterate_items(with_groups=False):
        label = _docling_label(item)
        text = str(getattr(item, "text", "") or "").strip()
        page = _page_number(item)
        if label == "section_header" and text:
            heading_level = int(getattr(item, "level", 1) or 1)
            while stack and stack[-1]["level"] >= heading_level:
                stack.pop()
            parent = stack[-1] if stack else None
            page_label = f"p{page or 0:06d}"
            parent_key = parent["key"] if parent else page_label
            sibling_counts[parent_key] = sibling_counts.get(parent_key, 0) + 1
            ordinal = sibling_counts[parent_key]
            key = f"{parent_key}.h{ordinal}"
            ancestors = [entry["title"] for entry in stack]
            breadcrumbs = [document_title]
            if page:
                breadcrumbs.append(f"Page {page}")
            breadcrumbs.extend([*ancestors, text])
            heading_path = [
                f"h{entry['ordinal']}_{_ltree_label(entry['title'], 'section')}" for entry in stack
            ]
            heading_path.append(f"h{ordinal}_{_ltree_label(text, 'section')}")
            path = ".".join([page_label, *heading_path])
            node = ParsedNode(
                title=text, text=text, breadcrumbs=breadcrumbs, path=path, node_type="section"
            )
            nodes.append(node)
            stack.append(
                {
                    "level": heading_level,
                    "title": text,
                    "key": key,
                    "page": page,
                    "ordinal": ordinal,
                    "node": node,
                }
            )
        elif text:
            if stack:
                stack[-1]["node"].text += "\n\n" + text
            else:
                preambles.setdefault(page, []).append(text)

    preamble_nodes = []
    for page, parts in sorted(preambles.items(), key=lambda entry: entry[0] or 0):
        page_label = f"p{page or 0:06d}"
        breadcrumbs = [document_title]
        if page:
            breadcrumbs.append(f"Page {page}")
        preamble_nodes.append(
            ParsedNode(
                title=document_title,
                text="\n\n".join(parts),
                breadcrumbs=breadcrumbs,
                path=page_label,
                node_type="preamble",
            )
        )
    nodes = preamble_nodes + nodes

    if not nodes:
        nodes.append(
            ParsedNode(
                title=document_title,
                text="",
                breadcrumbs=[document_title],
                path="n1",
                node_type="header",
            )
        )
    return nodes


def parse_document(path: str | Path) -> tuple[str, Any]:
    """Convert a supported file and return its title and structured document."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Uploaded file does not exist: {source}")
    # Explicitly select Russian OCR for scanned PDFs. Tesseract is installed in
    # the worker image with rus/eng traineddata; other formats retain Docling's
    # default converters.
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = True
    pdf_options.ocr_options = TesseractCliOcrOptions(lang=["rus", "eng"])
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        }
    )
    result = converter.convert(str(source))
    title = source.stem
    try:
        title = result.document.name or title
    except (AttributeError, TypeError):
        pass
    return title, result.document
