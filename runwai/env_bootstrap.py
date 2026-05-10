"""Load repository-root `.env` once before Layer 4 reads ``os.environ``."""

from __future__ import annotations

from pathlib import Path

_done = False


def load_repo_dotenv() -> None:
    global _done
    if _done:
        return
    _done = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
