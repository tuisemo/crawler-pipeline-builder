#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/Scripts/python.exe"

if [ ! -x "$VENV_PY" ]; then
  echo "Expected virtualenv python at $VENV_PY" >&2
  exit 1
fi

"$VENV_PY" -m pip install -e "$ROOT"

if [ ! -d "$ROOT/frontend" ]; then
  echo "React workbench not present yet; skipping frontend setup"
fi
