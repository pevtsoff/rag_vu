"""httpx MockTransport helpers for provider adapter tests."""

import json
from collections.abc import Callable

import httpx

from app.adapters.outbound.http_client_factory import HttpClientFactory

Handler = Callable[[httpx.Request], httpx.Response]


def mock_clients(handler: Handler) -> HttpClientFactory:
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def body(request: httpx.Request) -> dict:
    return json.loads(request.content)
