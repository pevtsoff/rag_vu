"""The chat prompt for grounded legal answers."""

from app.application.use_cases.query.reasoning_filter import remove_reasoning_leak
from app.application.use_cases.query.version_collapse import version_count
from app.application.use_cases.query.version_label import version_label
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
VERSION_INSTRUCTIONS = (
    "The context contains several versions of the same document; the [Doc: … | v… | …] line "
    "above each passage names its version. Compare the versions. For every difference, say "
    "which version it comes from. Say plainly when a passage is unchanged across versions "
    "(marked «без изменений»). If the user did not ask about history, answer from the latest "
    "version and mention earlier versions only where they differ."
)


def build_answer_messages(
    question: str,
    history: list[dict[str, str]],
    matches: list[RetrievedMatch],
    max_history_turns: int,
) -> list[dict[str, str]]:
    context = CONTEXT_SEPARATOR.join(_labelled(match) for match in matches) or EMPTY_CONTEXT
    instructions = SYSTEM_INSTRUCTIONS
    if version_count(matches) > 1:
        instructions = f"{SYSTEM_INSTRUCTIONS}\n\n{VERSION_INSTRUCTIONS}"
    system = {
        "role": "system",
        "content": f"{instructions}\n\nRetrieved context:\n{context}",
    }
    recent = history[-max_history_turns * 2 :] if max_history_turns > 0 else []
    return [system, *_clean_history(recent), {"role": "user", "content": question}]


def _labelled(match: RetrievedMatch) -> str:
    return f"{version_label(match.version)}\n{match.text}" if match.version else match.text


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
