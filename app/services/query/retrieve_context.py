"""Format retrieved passages and their source hierarchy."""

import re

from sqlalchemy import Text, cast, select

from app.models import Document, Node
from app.services.query.settings import settings as query_settings
from app.services.query.types import RetrievedMatch


def format_breadcrumbs(breadcrumbs) -> str:
    """Format stored breadcrumb values consistently for retrieval context."""
    if not breadcrumbs:
        return ""
    if isinstance(breadcrumbs, str):
        return breadcrumbs.strip()
    if isinstance(breadcrumbs, (list, tuple)):
        return " > ".join(str(item).strip() for item in breadcrumbs if item)
    if isinstance(breadcrumbs, dict):
        for key in ("items", "breadcrumbs", "path"):
            value = breadcrumbs.get(key)
            if isinstance(value, (list, tuple)):
                return " > ".join(str(item).strip() for item in value if item)
        return " > ".join(str(value).strip() for value in breadcrumbs.values() if value)
    return str(breadcrumbs).strip()


def build_retrieved_context(
    text: str,
    breadcrumbs,
    title: str | None = None,
    document_title: str | None = None,
) -> str:
    """Attach explicit source hierarchy to every retrieved passage."""
    hierarchy = format_breadcrumbs(breadcrumbs)
    if not hierarchy and title:
        hierarchy = title.strip()
    metadata = []
    if document_title:
        metadata.append(f"Документ: {document_title}")
    if hierarchy:
        metadata.append(f"Breadcrumbs: {hierarchy}")
    source_header = "\n".join(metadata)
    if source_header:
        return f"{source_header}\nТекст фрагмента:\n{text}"
    return text


async def retrieve_article_context(session, document_id, article_path):
    """Load a full article, falling back to its ordered article parts."""
    statement = (
        select(
            Node.id,
            Node.title,
            Node.breadcrumbs,
            Node.text,
            Document.file_name,
        )
        .join(Document, Document.id == Node.document_id)
        .where(Node.document_id == document_id)
    )
    article_result = await session.execute(
        statement.where(
            Node.node_type == "article",
            cast(Node.path, Text) == article_path,
        ).limit(1)
    )
    article = article_result.first()
    if article and article[3]:
        article_node_id, title, breadcrumbs, text, file_name = article
        sections_result = await session.execute(
            statement.where(
                Node.node_type.in_(("article_section", "article_part")),
                cast(Node.path, Text).like(f"{article_path}.%"),
            ).order_by(Node.path)
        )
        sections = sections_result.all()
        if sections:
            text = "\n\n".join([text, *(section[3] for section in sections if section[3])])
        return (
            build_retrieved_context(text, breadcrumbs, title, file_name),
            [str(article_node_id), *(str(section[0]) for section in sections)],
        )

    parts_result = await session.execute(
        statement.where(
            Node.node_type.in_(("article_section", "article_part")),
            cast(Node.path, Text).like(f"{article_path}.%"),
        ).order_by(Node.path)
    )
    parts = parts_result.all()
    if not parts:
        return None

    _, title, breadcrumbs, _, file_name = parts[0]
    text = "\n\n".join(part_text for _, _, _, part_text, _ in parts if part_text)
    return (
        build_retrieved_context(text, breadcrumbs, title, file_name),
        [str(part[0]) for part in parts],
    )


def append_source_links(answer: str, matches: list[RetrievedMatch]) -> str:
    """Append links to the article nodes whose passages were sent to the LLM."""
    source_heading = re.search(
        r"(?im)^\s*(?:\*\*|__)?(?:источники|sources):?(?:\*\*|__)?\s*$", answer
    )
    if source_heading:
        answer = answer[: source_heading.start()].rstrip()

    links: list[str] = []
    seen: set[str] = set()
    for match in matches:
        hierarchy_match = re.search(r"(?m)^Breadcrumbs: (.+)$", match.text)
        label = hierarchy_match.group(1) if hierarchy_match else "Открыть источник"
        label = " ".join(label.split())
        label = re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", label)
        for node_id in match.node_ids:
            if node_id in seen:
                continue
            seen.add(node_id)
            url = f"{query_settings.rag_vu_api_base_url.rstrip('/')}/api/v1/nodes/{node_id}/html"
            links.append(f"- [{label}]({url})")

    if not links:
        return answer
    return f"{answer.rstrip()}\n\n**Источники:**\n" + "\n".join(links)
