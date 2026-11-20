"""A chat-completion language model."""

from abc import ABC, abstractmethod


class ChatModel(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the assistant's raw reply to ``messages``."""
