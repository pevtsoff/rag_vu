"""Creates configured httpx clients; tests inject a mock transport instead."""

from collections.abc import Callable

import httpx

HttpClientFactory = Callable[[], httpx.AsyncClient]
DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=120, write=120, pool=120)


def default_http_client_factory(
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
) -> HttpClientFactory:
    def create() -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    return create
