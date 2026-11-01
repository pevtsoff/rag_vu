import io
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    HeadingHierarchyOptions,
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
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
    for item, _ in docling_document.iterate_items(with_groups=False):
        _append_docling_item(item, document_title, nodes, stack, sibling_counts, preambles)
    _prepend_preambles(nodes, preambles, document_title)
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


def _append_docling_item(
    item: Any, title: str, nodes: list[ParsedNode], stack: list[dict[str, Any]],
    sibling_counts: dict[str, int], preambles: dict[int | None, list[str]],
) -> None:
    text = str(getattr(item, "text", "") or "").strip()
    page = _page_number(item)
    if _docling_label(item) == "section_header" and text:
        _append_section_header(item, text, title, page, nodes, stack, sibling_counts)
    elif text and stack:
        stack[-1]["node"].text += "\n\n" + text
    elif text:
        preambles.setdefault(page, []).append(text)


def _append_section_header(
    item: Any, text: str, title: str, page: int | None, nodes: list[ParsedNode],
    stack: list[dict[str, Any]], sibling_counts: dict[str, int],
) -> None:
    level = int(getattr(item, "level", 1) or 1)
    while stack and stack[-1]["level"] >= level:
        stack.pop()
    page_label = f"p{page or 0:06d}"
    parent_key = stack[-1]["key"] if stack else page_label
    ordinal = sibling_counts.get(parent_key, 0) + 1
    sibling_counts[parent_key] = ordinal
    node = _make_section_node(text, title, page, stack, ordinal, page_label)
    nodes.append(node)
    stack.append({"level": level, "title": text, "key": f"{parent_key}.h{ordinal}",
                  "ordinal": ordinal, "node": node})


def _prepend_preambles(
    nodes: list[ParsedNode], preambles: dict[int | None, list[str]], title: str,
) -> None:
    preamble_nodes = []
    for page, parts in sorted(preambles.items(), key=lambda entry: entry[0] or 0):
        breadcrumbs = [title, *([f"Page {page}"] if page else [])]
        preamble_nodes.append(
            ParsedNode(title, "\n\n".join(parts), breadcrumbs, f"p{page or 0:06d}", "preamble")
        )
    nodes[:0] = preamble_nodes


def _make_section_node(
    text: str, title: str, page: int | None, stack: list[dict[str, Any]],
    ordinal: int, page_label: str,
) -> ParsedNode:
    ancestors = [entry["title"] for entry in stack]
    breadcrumbs = [title]
    if page:
        breadcrumbs.append(f"Page {page}")
    breadcrumbs.extend([*ancestors, text])
    heading_path = [
        f"h{entry['ordinal']}_{_ltree_label(entry['title'], 'section')}" for entry in stack
    ]
    heading_path.append(f"h{ordinal}_{_ltree_label(text, 'section')}")
    return ParsedNode(
        text,
        text,
        breadcrumbs,
        ".".join([page_label, *heading_path]),
        "section",
    )


def parse_document(path: str | Path) -> tuple[str, Any]:
    """Convert a supported file and return its title and structured document."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Uploaded file does not exist: {source}")
    # Explicitly select Russian OCR for scanned PDFs. Tesseract is installed in
    # the worker image with rus/eng traineddata; other formats retain Docling's
    # default converters.
    pdf_options = PdfPipelineOptions()
    pdf_options.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)
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


def extract_image_nodes(document: Any, document_folder: str | Path, title: str) -> list[ParsedNode]:
    """Save each Docling picture and OCR its text into a standalone source node."""
    image_folder = Path(document_folder) / "images"
    image_folder.mkdir(parents=True, exist_ok=True)
    image_nodes: list[ParsedNode] = []
    for index, item in enumerate(_picture_items(document), start=1):
        image = item.get_image(document) if hasattr(item, "get_image") else None
        if image is None:
            continue
        path = image_folder / f"image_{index:04d}.png"
        image.save(path)
        image_nodes.append(_image_node(path, image, index, title, item))
    return image_nodes


def _picture_items(document: Any) -> list[Any]:
    return [item for item, _ in document.iterate_items(with_groups=False) if _docling_label(item) in {"picture", "figure"}]


def _image_node(path: Path, image: Any, index: int, title: str, item: Any) -> ParsedNode:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result = subprocess.run(["tesseract", "stdin", "stdout", "-l", "rus+eng"], input=buffer.getvalue(), capture_output=True, check=True)
    text = result.stdout.decode("utf-8").strip()
    page = _page_number(item)
    breadcrumbs = [title, *([f"Page {page}"] if page else []), f"Image {index}"]
    return ParsedNode(f"Image {index}", text, breadcrumbs, f"img{index}_{_ltree_label(path.stem, 'image')}", "image")
