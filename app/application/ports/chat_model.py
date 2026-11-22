"""A chat-completion language model."""

from abc import ABC, abstractmethod

from app.application.dto.chat_completion import ChatCompletion


class ChatModel(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> ChatCompletion:
        """Return the assistant's raw reply to ``messages`` with model and token usage."""
