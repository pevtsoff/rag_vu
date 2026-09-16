"""Generate grounded answers from retrieved passages."""

import logging
import re

import httpx

from app.services.query.providers import require_free_model
from app.services.query.settings import settings as query_settings
from app.services.query.types import RetrievedMatch


def remove_reasoning_leak(answer: str) -> str | None:
    """Keep only a final answer if a model accidentally emits its analysis."""
    answer = answer.strip()
    reasoning_prefix = re.match(
        r"(?is)^(?:the user asks|we need to answer|we must answer|the context includes|"
        r"here(?:'s| is) (?:my )?(?:thinking process|analysis)|"
        r"analysis\s*:|reasoning\s*:|let me think|"
        r"ход рассуждений\s*:|рассуждение\s*:|анализ\s*:)",
        answer,
    )
    if not reasoning_prefix:
        return answer

    final_answer = re.search(
        r"(?is)(?:^|\n)\s*(?:final answer|answer|итоговый ответ|ответ)"
        r"\s*:\s*(.+)\Z",
        answer,
    )
    return final_answer.group(1).strip() if final_answer else None


def context_answer_fallback(matches: list[RetrievedMatch]) -> str:
    """Return the best retrieved passage instead of exposing model analysis."""
    if not matches:
        return "Не удалось сформировать ответ: модель вернула внутренний анализ."
    context = matches[0].text
    hierarchy_match = re.search(r"(?m)^Breadcrumbs: (.+)$", context)
    body_match = re.search(r"(?s)^.*?Текст фрагмента:\n(.*)$", context)
    hierarchy = hierarchy_match.group(1).strip() if hierarchy_match else ""
    body = body_match.group(1).strip() if body_match else context.strip()
    numbered_paragraph = re.search(r"(?m)^\s*\d+\.\s+(.+)$", body)
    if numbered_paragraph:
        body = numbered_paragraph.group(1).strip()
    sentence = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0]
    if hierarchy:
        return f"{sentence}\n\nИсточник: {hierarchy}"
    return sentence


def build_retrieval_query(query: str, history: list[dict[str, str]]) -> str:
    """Resolve short legal follow-ups using the preceding user question."""
    is_follow_up = bool(
        re.search(r"\bстать[еяи]\s+\d", query, re.IGNORECASE)
        or re.match(r"\s*(?:а|и|тогда|а что|и что)\b", query, re.IGNORECASE)
    )
    if is_follow_up:
        previous_questions = [
            item["content"]
            for item in reversed(history)
            if item.get("role") == "user" and item.get("content")
        ][:1]
        if previous_questions:
            return f"{previous_questions[0]}\n{query}"
    return query


async def generate_answer(
    client: httpx.AsyncClient,
    api_key: str | None,
    query: str,
    history: list[dict[str, str]],
    matches: list[RetrievedMatch],
) -> str:
    context = "\n\n---\n\n".join(match.text for match in matches)
    clean_history = []
    for item in history[-query_settings.max_history_turns * 2 :]:
        content = item.get("content", "")
        if item.get("role") == "assistant":
            content = remove_reasoning_leak(content) or ""
            if not content:
                continue
        clean_history.append({"role": item["role"], "content": content})
    messages = [
        {
            "role": "system",
            "content": (
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
                "sources section; the application appends verified source links.\n\n"
                f"Retrieved context:\n{context or '(No matching chunks found.)'}"
            ),
        },
        *clean_history,
        {"role": "user", "content": query},
    ]
    provider = query_settings.query_llm_provider.strip().lower()
    if provider == "ollama":
        return await generate_answer_with_ollama(client, messages, matches)
    if provider != "openrouter":
        raise RuntimeError("QUERY_LLM_PROVIDER must be 'ollama' or 'openrouter'.")
    if not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY to use OpenRouter chat.")

    model = require_free_model(
        query_settings.openrouter_chat_model,
        "OPENROUTER_CHAT_MODEL",
    )
    fallback_models = [
        require_free_model(fallback.strip(), "OPENROUTER_CHAT_FALLBACK_MODELS")
        for fallback in query_settings.openrouter_chat_fallback_models.split(",")
        if fallback.strip() and fallback.strip() != model
    ]
    model_chain = [model, *fallback_models]
    response = await client.post(
        f"{query_settings.openrouter_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "models": model_chain,
            "messages": messages,
            "max_tokens": 1000,
            "reasoning": {"enabled": True, "effort": "low", "exclude": True},
        },
    )

    try:
        payload = response.json()
    except ValueError as exc:
        response.raise_for_status()
        raise RuntimeError(
            f"OpenRouter returned a non-JSON response (HTTP {response.status_code})."
        ) from exc

    if not response.is_success:
        error_payload = payload.get("error", payload) if isinstance(payload, dict) else payload
        detail = str(error_payload)[:1000]
        raise RuntimeError(
            f"OpenRouter chat request failed (HTTP {response.status_code}): {detail}"
        )

    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        detail = str(payload)[:1000]
        logging.getLogger(__name__).error(
            "OpenRouter returned no choices for model chain %s (HTTP %s): %s",
            model_chain,
            response.status_code,
            detail,
        )
        raise RuntimeError(
            f"OpenRouter model chain {model_chain!r} returned no answer. Response: {detail}"
        )

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError(f"OpenRouter returned an invalid choice: {first_choice!r}")

    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        raise RuntimeError(f"OpenRouter returned an invalid message: {message!r}")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        finish_reason = first_choice.get("finish_reason", "unknown")
        if finish_reason == "length":
            logging.getLogger(__name__).warning(
                "OpenRouter exhausted the completion budget before returning answer text."
            )
            raise RuntimeError(
                "OpenRouter exhausted the completion budget before returning answer text "
                "(finish_reason='length'). Try again with less retrieved context or use a "
                "model with a larger completion budget."
            )
        raise RuntimeError(
            f"OpenRouter model chain {model_chain!r} returned an empty answer. "
            f"Finish reason: {finish_reason}"
        )
    clean_content = remove_reasoning_leak(content)
    if clean_content:
        return clean_content

    logging.getLogger(__name__).warning("Chat model returned analysis instead of a final answer.")
    raise RuntimeError("The chat model returned reasoning without a final answer.")


async def generate_answer_with_ollama(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    matches: list[RetrievedMatch],
) -> str:
    """Generate the answer through the configured Ollama HTTP service."""
    model = query_settings.ollama_model.strip()
    if not model:
        raise RuntimeError("OLLAMA_MODEL cannot be empty.")
    response = await client.post(
        f"{query_settings.ollama_base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 400},
        },
        timeout=query_settings.ollama_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    output = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(output, str) or not output.strip():
        logging.getLogger(__name__).warning("Ollama returned an empty answer.")
        raise RuntimeError("Ollama returned an empty answer.")
    clean_output = remove_reasoning_leak(output)
    if clean_output:
        return clean_output

    logging.getLogger(__name__).warning("Ollama returned reasoning without a final answer.")
    raise RuntimeError("Ollama returned reasoning without a final answer.")
