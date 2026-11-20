"""Only free OpenRouter models may be used, so the service never incurs charges."""

FREE_ROUTER_MODEL = "openrouter/free"


def require_free_model(model: str, setting_name: str) -> str:
    if model == FREE_ROUTER_MODEL or model.endswith(":free"):
        return model
    raise RuntimeError(
        f"{setting_name} must use a free model ID ending in ':free' "
        "or 'openrouter/free'; paid model IDs are disabled."
    )


def free_model_chain(model: str, fallbacks: str) -> list[str]:
    """The primary chat model followed by distinct comma-separated fallbacks."""
    primary = require_free_model(model, "OPENROUTER_CHAT_MODEL")
    extra = [
        require_free_model(fallback.strip(), "OPENROUTER_CHAT_FALLBACK_MODELS")
        for fallback in fallbacks.split(",")
        if fallback.strip() and fallback.strip() != primary
    ]
    return [primary, *extra]
