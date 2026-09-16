"""Shared provider configuration helpers for the query service."""

from app.services.query.settings import settings as query_settings


def get_api_key() -> str:
    """Return the configured OpenRouter key or explain how to configure it."""
    api_key = query_settings.openrouter_api_key
    if not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY in the environment or .env file.")
    return api_key


def require_free_model(model: str, setting_name: str) -> str:
    """Reject model IDs that can incur inference charges."""
    if model == "openrouter/free" or model.endswith(":free"):
        return model
    raise RuntimeError(
        f"{setting_name} must use a free model ID ending in ':free' "
        "or 'openrouter/free'; paid model IDs are disabled."
    )
