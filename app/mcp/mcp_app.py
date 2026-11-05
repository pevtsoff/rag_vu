"""MCP server exposing RAG-VU document management tools."""

import mimetypes
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastmcp import FastMCP

from app.settings import settings

mcp = FastMCP("RAG-VU")


async def _api_request(method: str, path: str, **kwargs: Any) -> Any:
    """Send a request to the RAG-VU API and return its JSON response."""
    base_url = settings.rag_vu_api_base_url.rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()


@mcp.tool
async def upload_a_file(file_path: str, force_run: bool = False) -> dict[str, Any]:
    """Upload a local file to RAG-VU and start document processing."""
    path = Path(file_path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Not a regular file: {path}")
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as file_data:
        return await _api_request(
            "POST",
            "/api/v1/documents/upload",
            params={"force_run": force_run},
            files={"file": (path.name, file_data, mime_type)},
        )


@mcp.tool
async def rerun_pipeline(
    document_id: UUID, stage: str = "parsing", force_run: bool = True
) -> dict[str, Any]:
    """Rerun a document pipeline from uploading, parsing, or chunking."""
    allowed_stages = {"uploading", "parsing", "chunking"}
    if stage not in allowed_stages:
        raise ValueError(f"stage must be one of: {', '.join(sorted(allowed_stages))}")
    return await _api_request(
        "GET",
        f"/api/v1/documents/{document_id}/rerun/{stage}",
        params={"force_run": force_run},
    )


@mcp.tool
async def get_document(document_id: UUID) -> dict[str, Any]:
    """Get document metadata and current processing status by UUID."""
    return await _api_request("GET", f"/api/v1/documents/{document_id}")


def main() -> None:
    """Start the MCP server using the configured transport."""
    if settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
        return
    mcp.run(transport="http", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
