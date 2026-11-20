"""Accessors for Docling document items, which expose data through optional attributes."""

from typing import Any


def docling_label(item: Any) -> str:
    label = getattr(item, "label", "")
    return str(getattr(label, "value", label)).lower()


def page_number(item: Any) -> int | None:
    provenance = getattr(item, "prov", None) or []
    numbers = [getattr(entry, "page_no", None) for entry in provenance]
    numbers = [number for number in numbers if isinstance(number, int) and number > 0]
    return min(numbers) if numbers else None


def item_text(item: Any) -> str:
    return str(getattr(item, "text", "") or "").strip()


def item_ref(item: Any) -> str:
    return str(getattr(item, "self_ref", id(item)))


def heading_level(item: Any) -> int:
    level = getattr(item, "level", 1)
    return level if isinstance(level, int) and level > 0 else 1


def page_label(page: int | None) -> str:
    return f"p{page or 0:06d}"
