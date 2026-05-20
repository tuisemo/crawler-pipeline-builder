#!/usr/bin/env python3
"""
setup.py — Backend environment setup helper
=============================================

Idempotent setup script that installs Playwright browsers if missing.

Usage:
    uv run python scripts/setup.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _playwright_cli() -> list[str]:
    return [sys.executable, "-m", "playwright"]


def _chromium_executable_path() -> str | None:
    """Resolve the expected chromium executable path without launching anything."""
    try:
        from playwright._impl._driver import compute_driver_executable  # type: ignore[import-untyped]
    except (ImportError, Exception):
        return None
    try:
        result = subprocess.run(
            _playwright_cli() + ["install", "--dry-run", "chromium"],
            capture_output=True, text=True,
        )
        # --dry-run prints the path and exits 0 when already installed
        if result.returncode == 0:
            return "ok"
    except Exception:
        pass
    return None


def _is_chromium_installed() -> bool:
    """Check if Playwright chromium browser binary exists on disk."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print(p.chromium.executable_path or ''); p.stop()"],
            capture_output=True, text=True, timeout=10,
        )
        exe_path = result.stdout.strip()
        if exe_path and Path(exe_path).exists():
            return True
    except Exception:
        pass
    return False


def install_playwright_browsers() -> None:
    """Install Playwright chromium browser if not already present."""
    print("[setup] Checking Playwright browsers...")
    if _is_chromium_installed():
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
