"""Remove model reasoning that leaks into an answer."""

import re

from app.domain.retrieval.retrieved_match import RetrievedMatch

_REASONING_PREFIX = re.compile(
    r"(?is)^(?:the user asks|we need to answer|we must answer|the context includes|"
    r"here(?:'s| is) (?:my )?(?:thinking process|analysis)|"
    r"analysis\s*:|reasoning\s*:|let me think|"
    r"ход рассуждений\s*:|рассуждение\s*:|анализ\s*:)"
)
_FINAL_ANSWER = re.compile(
    r"(?is)(?:^|\n)\s*(?:final answer|answer|итоговый ответ|ответ)\s*:\s*(.+)\Z"
)
NO_ANSWER_MESSAGE = "Не удалось сформировать ответ: модель вернула внутренний анализ."


def remove_reasoning_leak(answer: str) -> str | None:
    """Return the answer without analysis, or None if only analysis was returned."""
    answer = answer.strip()
    if not _REASONING_PREFIX.match(answer):
        return answer
    final_answer = _FINAL_ANSWER.search(answer)
    return final_answer.group(1).strip() if final_answer else None


def context_answer_fallback(matches: list[RetrievedMatch]) -> str:
    """Answer with the first sentence of the best passage instead of model analysis."""
    if not matches:
        return NO_ANSWER_MESSAGE
    context = matches[0].text
    hierarchy_match = re.search(r"(?m)^Breadcrumbs: (.+)$", context)
    body_match = re.search(r"(?s)^.*?Текст фрагмента:\n(.*)$", context)
    hierarchy = hierarchy_match.group(1).strip() if hierarchy_match else ""
    body = body_match.group(1).strip() if body_match else context.strip()
    numbered_paragraph = re.search(r"(?m)^\s*\d+\.\s+(.+)$", body)
    if numbered_paragraph:
        body = numbered_paragraph.group(1).strip()
    sentence = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0]
    return f"{sentence}\n\nИсточник: {hierarchy}" if hierarchy else sentence
