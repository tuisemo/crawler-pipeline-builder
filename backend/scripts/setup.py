#!/usr/bin/env python3
"""
setup.py — Backend environment setup helper
=============================================

Idempotent setup script that installs Playwright browsers if missing.

Usage:
    uv run python scripts/setup.py
    # or after `pip install -e .`:
    backend-setup
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _playwright_cli() -> list[str]:
    """Return the playwright CLI command prefix (handles venv / uvx)."""
    # Prefer the playwright executable next to the current Python
    import playwright
    bin_dir = playwright.__file__
    # playwright package is installed; use the CLI from the same env
    return [sys.executable, "-m", "playwright"]


def _browsers_installed() -> bool:
    """Check if chromium is already installed."""
    try:
        result = subprocess.run(
            _playwright_cli() + ["install", "--dry-run", "chromium"],
            capture_output=True, text=True,
        )
        # --dry-run returns 0 when already installed
        return result.returncode == 0
    except Exception:
        return False


def install_playwright_browsers() -> None:
    """Install Playwright chromium browser if not already present."""
    print("[setup] Checking Playwright browsers...")
    if _browsers_installed():
        print("[setup] Playwright chromium already installed, skipping.")
        return

    print("[setup] Installing Playwright chromium browser...")
    cmd = _playwright_cli() + ["install", "chromium"]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[setup] ERROR: playwright install chromium failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(1)
    print("[setup] Playwright chromium installed successfully.")


def main() -> None:
    install_playwright_browsers()


if __name__ == "__main__":
    main()
