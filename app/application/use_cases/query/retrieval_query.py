"""Resolve short legal follow-up questions against the conversation."""

import re

_ARTICLE_REFERENCE = re.compile(r"\bстать[еяи]\s+\d", re.IGNORECASE)
_FOLLOW_UP_OPENING = re.compile(r"\s*(?:а|и|тогда|а что|и что)\b", re.IGNORECASE)


def build_retrieval_query(query: str, history: list[dict[str, str]]) -> str:
    """Prefix a follow-up with the previous user question so retrieval keeps its topic."""
    if not (_ARTICLE_REFERENCE.search(query) or _FOLLOW_UP_OPENING.match(query)):
        return query
    previous = next(
        (
            item["content"]
            for item in reversed(history)
            if item.get("role") == "user" and item.get("content")
        ),
        None,
    )
    return f"{previous}\n{query}" if previous else query
