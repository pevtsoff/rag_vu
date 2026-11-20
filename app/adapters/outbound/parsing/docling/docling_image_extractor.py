"""Saves each Docling picture and turns its OCR text into a standalone node."""

import io
from pathlib import Path
from typing import Any

from app.adapters.outbound.parsing.docling.docling_items import docling_label, page_number
from app.adapters.outbound.parsing.image_text_recognizer import ImageTextRecognizer
from app.adapters.outbound.parsing.ltree_label import ltree_label
from app.domain.documents.node_type import NodeType
from app.domain.documents.parsed_node import ParsedNode

PICTURE_LABELS = frozenset({"picture", "figure"})


class DoclingImageExtractor:
    def __init__(self, recognizer: ImageTextRecognizer) -> None:
        self._recognizer = recognizer

    def extract(self, document: Any, folder: str | Path, title: str) -> list[ParsedNode]:
        image_folder = Path(folder) / "images"
        image_folder.mkdir(parents=True, exist_ok=True)
        nodes: list[ParsedNode] = []
        for index, item in enumerate(_picture_items(document), start=1):
            image = item.get_image(document) if hasattr(item, "get_image") else None
            if image is None:
                continue
            path = image_folder / f"image_{index:04d}.png"
            image.save(path)
            nodes.append(self._image_node(path, image, index, title, item))
        return nodes

    def _image_node(self, path: Path, image: Any, index: int, title: str, item: Any) -> ParsedNode:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        text = self._recognizer.recognize(buffer.getvalue())
        page = page_number(item)
        breadcrumbs = [title, *([f"Page {page}"] if page else []), f"Image {index}"]
        node_path = f"img{index}_{ltree_label(path.stem, 'image')}"
        return ParsedNode(f"Image {index}", text, breadcrumbs, node_path, NodeType.IMAGE.value)


def _picture_items(document: Any) -> list[Any]:
    return [
        item
        for item, _ in document.iterate_items(with_groups=False)
        if docling_label(item) in PICTURE_LABELS
    ]
