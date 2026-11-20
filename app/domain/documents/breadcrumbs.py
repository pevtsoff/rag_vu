"""Formatting of stored breadcrumb values, which may come in several shapes."""

from collections.abc import Iterable

_LIST_KEYS = ("items", "breadcrumbs", "path")


def join_breadcrumbs(breadcrumbs: object, separator: str) -> str:
    """Join a breadcrumb list, dict, or string into one line of hierarchy."""
    if not breadcrumbs:
        return ""
    if isinstance(breadcrumbs, str):
        return breadcrumbs.strip()
    if isinstance(breadcrumbs, (list, tuple)):
        return _join(breadcrumbs, separator)
    if isinstance(breadcrumbs, dict):
        for key in _LIST_KEYS:
            value = breadcrumbs.get(key)
            if isinstance(value, (list, tuple)):
                return _join(value, separator)
        return _join(breadcrumbs.values(), separator)
    return str(breadcrumbs).strip()


def _join(items: Iterable[object], separator: str) -> str:
    return separator.join(str(item).strip() for item in items if str(item).strip())
