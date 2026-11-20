"""Append verified source links to an answer."""

import re

from app.domain.retrieval.retrieved_match import RetrievedMatch

_SOURCES_HEADING = re.compile(r"(?im)^\s*(?:\*\*|__)?(?:источники|sources):?(?:\*\*|__)?\s*$")
_HIERARCHY = re.compile(r"(?m)^Breadcrumbs: (.+)$")
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>])")


def append_source_links(answer: str, matches: list[RetrievedMatch], api_base_url: str) -> str:
    """Replace any model-written sources with links to every node sent to the model."""
    heading = _SOURCES_HEADING.search(answer)
    if heading:
        answer = answer[: heading.start()].rstrip()
    links = _source_links(matches, api_base_url.rstrip("/"))
    if not links:
        return answer
    return f"{answer.rstrip()}\n\n**Источники:**\n" + "\n".join(links)


def _source_links(matches: list[RetrievedMatch], base_url: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for match in matches:
        label = _link_label(match.text)
        for node_id in match.node_ids:
            if node_id not in seen:
                seen.add(node_id)
                links.append(f"- [{label}]({base_url}/api/v1/nodes/{node_id}/html)")
    return links


def _link_label(text: str) -> str:
    hierarchy = _HIERARCHY.search(text)
    label = " ".join((hierarchy.group(1) if hierarchy else "Открыть источник").split())
    return _MARKDOWN_SPECIAL.sub(r"\\\1", label)
