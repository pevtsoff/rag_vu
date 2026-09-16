"""Chainlit chat handlers coordinating the query services."""

import chainlit as cl  # noqa: E402
import httpx  # noqa: E402

from app.services.query.bootstrap import configure_query_environment  # noqa: E402

configure_query_environment()

from app.services.embeddings import embedding_provider  # noqa: E402
from app.services.query.answer import build_retrieval_query, generate_answer  # noqa: E402
from app.services.query.providers import get_api_key  # noqa: E402
from app.services.query.rerank import rerank_chunks  # noqa: E402
from app.services.query.retrieve_context import append_source_links  # noqa: E402
from app.services.query.search_chunks import (  # noqa: E402
    embed_query,
    engine,
    search_chunks,
)
from app.services.query.settings import settings as query_settings  # noqa: E402


@cl.on_chat_start
async def on_chat_start() -> None:
    cl.user_session.set("history", [])
    await cl.Message(
        content=(
            "Ask a question about the indexed legal documents. "
            "I’ll retrieve the closest passages and answer from those excerpts."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    history: list[dict[str, str]] = cl.user_session.get("history") or []

    try:
        api_key = query_settings.openrouter_api_key
        if embedding_provider() == "openrouter" and not api_key:
            api_key = get_api_key()
        if query_settings.query_llm_provider.strip().lower() == "openrouter":
            if not api_key:
                api_key = get_api_key()
        timeout = httpx.Timeout(connect=10, read=120, write=120, pool=30)
        async with httpx.AsyncClient(timeout=timeout) as client:
            retrieval_query = build_retrieval_query(message.content, history)
            query_embedding = await embed_query(client, retrieval_query, api_key)
            candidates = await search_chunks(query_embedding, retrieval_query)
            matches = await rerank_chunks(client, api_key, retrieval_query, candidates)
            answer = await generate_answer(
                client=client,
                api_key=api_key,
                query=message.content,
                history=history,
                matches=matches,
            )
            answer = append_source_links(answer, matches)

        history.extend(
            [
                {"role": "user", "content": message.content},
                {"role": "assistant", "content": answer},
            ]
        )
        cl.user_session.set("history", history[-query_settings.max_history_turns * 2 :])
        await cl.Message(content=answer).send()
    except Exception as exc:
        await cl.Message(content=f"Query failed: {exc}").send()


@cl.on_chat_end
async def on_chat_end() -> None:
    await engine.dispose()
