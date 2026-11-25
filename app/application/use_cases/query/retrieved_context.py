"""Presentation of a retrieved passage with its source hierarchy."""

from app.domain.documents.breadcrumbs import join_breadcrumbs

HIERARCHY_SEPARATOR = " > "
PASSAGE_MARKER = "\nТекст фрагмента:\n"


def format_breadcrumbs(breadcrumbs: object) -> str:
    return join_breadcrumbs(breadcrumbs, HIERARCHY_SEPARATOR)


def build_retrieved_context(
    text: str,
    breadcrumbs: object,
    title: str | None = None,
    document_title: str | None = None,
) -> str:
    """Attach the document and breadcrumb hierarchy to a passage sent to the model."""
    hierarchy = format_breadcrumbs(breadcrumbs) or (title or "").strip()
    metadata = []
    if document_title:
        metadata.append(f"Документ: {document_title}")
    if hierarchy:
        metadata.append(f"Breadcrumbs: {hierarchy}")
    if not metadata:
        return text
    return "\n".join(metadata) + f"{PASSAGE_MARKER}{text}"


def retrieved_passage(context: str) -> str:
    """The passage text of ``build_retrieved_context`` output, without its metadata lines."""
    _, marker, passage = context.partition(PASSAGE_MARKER)
    return passage if marker else context
