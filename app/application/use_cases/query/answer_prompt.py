"""The chat prompt for grounded legal answers."""

from app.application.use_cases.query.reasoning_filter import remove_reasoning_leak
from app.domain.retrieval.retrieved_match import RetrievedMatch

CONTEXT_SEPARATOR = "\n\n---\n\n"
EMPTY_CONTEXT = "(No matching chunks found.)"
SYSTEM_INSTRUCTIONS = (
    "Answer questions about legal text concisely. For simple factual "
    "questions, answer concisely and give the requested fact. For every "
    "answer based on retrieved text, ALWAYS include the section number "
    "and full section title, plus the article number and full article "
    "title, copied from that passage's Breadcrumbs metadata. Use the "
    "format: Раздел <number> «<title>», статья <number> «<title>». "
    "If a breadcrumb does not contain one of these fields, say it is "
    "missing; never guess or invent it. Output only the final answer. "
    "Never include analysis, reasoning, planning, numbered thought "
    "steps, or a 'thinking process'. Respond in the user's language. "
    "Use the retrieved context as your source of truth. If it does not "
    "contain the answer, say so. Do not invent legal rules. Do not quote "
    "or list retrieved passages unless the user asks. Do not add a "
    "sources section; the application appends verified source links."
)


def build_answer_messages(
    question: str,
    history: list[dict[str, str]],
    matches: list[RetrievedMatch],
    max_history_turns: int,
) -> list[dict[str, str]]:
    context = CONTEXT_SEPARATOR.join(match.text for match in matches) or EMPTY_CONTEXT
    system = {
        "role": "system",
        "content": f"{SYSTEM_INSTRUCTIONS}\n\nRetrieved context:\n{context}",
    }
    recent = history[-max_history_turns * 2 :] if max_history_turns > 0 else []
    return [system, *_clean_history(recent), {"role": "user", "content": question}]


def _clean_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned = []
    for item in history:
        content = item.get("content", "")
        if item.get("role") == "assistant":
            content = remove_reasoning_leak(content) or ""
            if not content:
                continue
        cleaned.append({"role": item["role"], "content": content})
    return cleaned
