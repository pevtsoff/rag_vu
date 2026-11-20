"""Chainlit chat UI: ``chainlit run app/adapters/inbound/chat_ui/chat.py``."""

import os

import chainlit as cl

from app.bootstrap.infrastructure import Infrastructure
from app.bootstrap.query_container import QueryContainer
from app.config.app_settings import get_settings

WELCOME = (
    "Ask a question about the indexed legal documents. "
    "I’ll retrieve the closest passages and answer from those excerpts."
)

settings = get_settings()
# Chainlit treats DATABASE_URL as its own data layer; ours is already read into settings.
os.environ.pop("DATABASE_URL", None)
infrastructure = Infrastructure(settings)
answer_question = QueryContainer(infrastructure).answer_question


@cl.on_chat_start
async def on_chat_start() -> None:
    cl.user_session.set("history", [])
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    history: list[dict[str, str]] = cl.user_session.get("history") or []
    try:
        answer = await answer_question.execute(
            message.content, history, session_id=cl.context.session.id
        )
    except Exception as exc:
        await cl.Message(content=f"Query failed: {exc}").send()
        return
    history.extend(
        [{"role": "user", "content": message.content}, {"role": "assistant", "content": answer}]
    )
    cl.user_session.set("history", history[-settings.max_history_turns * 2 :])
    await cl.Message(content=answer).send()


@cl.on_chat_end
async def on_chat_end() -> None:
    # The engine is shared by every chat session, so it stays open for the process.
    return None
