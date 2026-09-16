"""Chainlit entry point for the RAG-VU query service."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.query.bootstrap import configure_query_environment  # noqa: E402

configure_query_environment()

# Import registers Chainlit callbacks.
if __name__ != "__main__":
    from app.services.query import chat as _chat  # noqa: E402,F401

if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "chainlit",
                "run",
                str(PROJECT_ROOT / "app/services/query/chat.py"),
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ]
        )
    )
