"""ASGI entry point: ``uvicorn app.main:app``."""

from app.adapters.inbound.http.app_factory import create_app
from app.bootstrap.api_container import ApiContainer
from app.bootstrap.infrastructure import Infrastructure
from app.config.app_settings import get_settings

container = ApiContainer(Infrastructure(get_settings()))
app = create_app(container, on_shutdown=container.dispose)
