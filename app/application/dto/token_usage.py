from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    """Token counts reported by a model provider; None when the provider omits one."""

    prompt: int | None = None
    completion: int | None = None
    total: int | None = None
