from dataclasses import dataclass, field

from app.application.dto.token_usage import TokenUsage


@dataclass(frozen=True)
class ChatCompletion:
    """The assistant's raw reply together with what the provider reported about it."""

    text: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str | None = None
