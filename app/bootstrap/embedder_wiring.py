from app.adapters.outbound.embeddings.ollama_embedder import OllamaEmbedder
from app.adapters.outbound.embeddings.openrouter_embedder import OpenRouterEmbedder
from app.adapters.outbound.http_client_factory import HttpClientFactory
from app.application.ports.embedder import Embedder
from app.config.app_settings import AppSettings


def create_embedder(settings: AppSettings, client_factory: HttpClientFactory) -> Embedder:
    """Chunk and query vectors must come from the same provider and size."""
    if settings.normalized_embedding_provider == "ollama":
        return OllamaEmbedder(
            client_factory, settings.ollama_base_url, settings.ollama_embedding_model
        )
    return OpenRouterEmbedder(
        client_factory,
        settings.openrouter_url,
        settings.openrouter_api_key,
        settings.openrouter_embedding_model,
    )
