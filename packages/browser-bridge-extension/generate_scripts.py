"""
Run inside packages/browser-bridge-extension:
  python generate_scripts.py

Regenerate script modules used by the Chrome extension worker.

- auto_detect.ts: extracted from backend/extraction/auto_detector.py (Python -> JS)
- highlight.ts, html_extract.ts, builtins.ts: copied from src/scripts/ source-of-truth files
  (these are hand-edited directly; this script just ensures the dist stays in sync)
"""

from pathlib import Path
import shutil

ROOT = Path(__file__).parent
REPO_ROOT = ROOT.parents[1]
BACKEND = REPO_ROOT / "backend"
OUT = ROOT / "src" / "scripts"


def extract(src_path: Path, var_name: str, strip_iife: bool = False) -> str:
    """Extract a triple-quoted JS string from a Python source file."""
    import re
    text = src_path.read_text(encoding="utf-8")
    match = re.search(rf"{var_name}\s*=\s*\"\"\"(.+?)\"\"\"", text, re.DOTALL)
    if not match:
        raise ValueError(f"{var_name} not found in {src_path}")
    js = match.group(1).strip()
    if strip_iife:
        iife = re.match(r"^\(\)\s*=>\s*\{(.*)\}\s*$", js, re.DOTALL)
        if iife:
            js = iife.group(1).strip()
    return js


OUT.mkdir(parents=True, exist_ok=True)

# --- auto_detect.ts: generated from Python backend ---
import re as _re  # noqa: E402
auto_detect = extract(BACKEND / "extraction" / "auto_detector.py", "JS_AUTO_DETECT", strip_iife=True)
(OUT / "auto_detect.ts").write_text(
    f"export function bridge_auto_detect() {{\n{auto_detect}\n}}\n",
    encoding="utf-8",
)
print("generated auto_detect.ts")

# --- highlight.ts, html_extract.ts, builtins.ts: source-of-truth lives in src/scripts/ ---
# These files are edited directly in src/scripts/ and should NOT be regenerated
# from hardcoded templates.  The canonical versions are the .ts files themselves.
for name in ("highlight.ts", "html_extract.ts", "builtins.ts"):
    src = OUT / name
    if src.exists():
        print(f"kept {name} (source of truth)")
    else:
        print(f"WARNING: {name} not found in {OUT}")
