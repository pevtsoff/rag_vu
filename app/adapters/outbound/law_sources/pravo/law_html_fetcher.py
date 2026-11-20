"""Downloads a law page and decodes it with the encoding it declares."""

import re
from collections.abc import Callable

import httpx

from app.application.errors import LawImportError

FETCH_TIMEOUT_SECONDS = 30.0
FALLBACK_ENCODING = "windows-1251"


def fetch_law_html(url: str, http_get: Callable[..., httpx.Response] = httpx.get) -> str:
    try:
        response = http_get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LawImportError(f"Failed to fetch document {url}: {exc}") from exc
    charset = re.search(
        r"charset\s*=\s*['\"]?([\w-]+)", response.headers.get("content-type", ""), re.IGNORECASE
    )
    if charset:
        response.encoding = charset.group(1)
    elif not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = FALLBACK_ENCODING
    return response.text
