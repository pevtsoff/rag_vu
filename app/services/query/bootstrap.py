"""Prepare environment variables before loading Chainlit or database modules."""

import os
from pathlib import Path

from dotenv import load_dotenv

from app.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def configure_query_environment() -> None:
    """Load the shared app settings before removing Chainlit's DB variable."""
    load_dotenv(PROJECT_ROOT / ".env")
    # Query uses the same cached settings and engine configuration as the API.
    get_settings()
    os.environ.pop("DATABASE_URL", None)
