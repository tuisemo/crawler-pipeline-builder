"""Git-based version identification for the backend service."""

from __future__ import annotations

import logging
import subprocess
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/


@lru_cache(maxsize=1)
def get_git_commit_hash() -> str:
    """Return the full git commit hash.

    Falls back to ``"unknown"`` when git is not available or the
    working directory is not inside a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = result.stdout.strip()
        if commit:
            return commit
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    logger.warning("Could not determine git commit hash, falling back to 'unknown'")
    return "unknown"
