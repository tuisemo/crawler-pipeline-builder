"""
Run inside packages/sea-extension:
  python extract_js.py

Extract browser JS strings from the backend and regenerate script modules used
by the Chrome extension worker.
"""

from pathlib import Path
import re

ROOT = Path(__file__).parent
REPO_ROOT = ROOT.parents[1]
BACKEND = REPO_ROOT / "backend"
OUT = ROOT / "src" / "scripts"


def extract(src_path: Path, var_name: str) -> str:
    text = src_path.read_text(encoding="utf-8")
    match = re.search(rf"{var_name}\s*=\s*\"\"\"(.+?)\"\"\"", text, re.DOTALL)
    if not match:
        raise ValueError(f"{var_name} not found in {src_path}")
    return match.group(1).strip()


OUT.mkdir(parents=True, exist_ok=True)

auto_detect = extract(BACKEND / "extraction" / "auto_detector.py", "JS_AUTO_DETECT")
(OUT / "auto_detect.ts").write_text(
    f"export function sea_auto_detect() {{\n{auto_detect}\n}}\n",
    encoding="utf-8",
)
print("generated auto_detect.ts")

highlight_ts = """
export function sea_highlight(selector: string, clearAfterMs: number) {
  const attr = "data-crawler-workflow-selector-highlight";
  const styleId = "crawler-workflow-selector-highlight-style";
  document.querySelectorAll(`[${attr}]`).forEach((el) => el.removeAttribute(attr));
  document.getElementById(styleId)?.remove();
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = `[${attr}] { outline: 3px solid #ef4444 !important; outline-offset: 2px !important; box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.18) !important; background-color: rgba(251, 191, 36, 0.18) !important; }`;
  document.head.appendChild(style);
  const els = document.querySelectorAll(selector);
  els.forEach((el, index) => {
    el.setAttribute(attr, "true");
    if (index === 0) {
      (el as HTMLElement).scrollIntoView?.({ block: "center", inline: "nearest", behavior: "instant" as ScrollBehavior });
    }
  });
  if (clearAfterMs > 0) {
    window.setTimeout(() => sea_clear_highlight(), clearAfterMs);
  }
  return { highlighted_count: els.length };
}

export function sea_clear_highlight() {
  const attr = "data-crawler-workflow-selector-highlight";
  const styleId = "crawler-workflow-selector-highlight-style";
  document.querySelectorAll(`[${attr}]`).forEach((el) => el.removeAttribute(attr));
  document.getElementById(styleId)?.remove();
  return { ok: true };
}
""".strip()
(OUT / "highlight.ts").write_text(f"{highlight_ts}\n", encoding="utf-8")
print("generated highlight.ts")

html_extract_ts = """
function cleanHtml(html: string) {
  return html.replace(/\\s+/g, " ").replace(/>\\s+</g, "><").trim();
}

export function sea_extract_html(selector: string, maxItems = 3) {
  const MAX = 15 * 1024;
  try {
    const els = [...document.querySelectorAll(selector)].slice(0, maxItems);
    let html = els.map((el) => cleanHtml(el.outerHTML)).join("\\n");
    const originalSize = new TextEncoder().encode(html).length;
    let truncated = false;
    if (originalSize > MAX) {
      truncated = true;
      html = html.slice(0, MAX) + "\\n<!-- TRUNCATED -->";
    }
    const truncatedSize = new TextEncoder().encode(html).length;
    return { html, truncated, original_size: originalSize, truncated_size: truncatedSize, item_count: els.length };
  } catch (e: any) {
    return { html: "", truncated: false, original_size: 0, truncated_size: 0, item_count: 0, error: e.message };
  }
}

export function sea_extract_html_with_pagination(selector: string, maxItems = 3) {
  const base = sea_extract_html(selector, maxItems);
  const pagSelectors = [".pagination", ".pager", "[class*=pagination]", "[class*=pager]", "nav[aria-label*=page i]", "nav"];
  let pagHtml = "";
  for (const candidate of pagSelectors) {
    const el = document.querySelector(candidate);
    if (el) {
      pagHtml = cleanHtml(el.outerHTML).slice(0, 3000);
      break;
    }
  }
  const html = pagHtml ? `<!-- ITEM_SAMPLES -->\\n${base.html}\\n<!-- PAGINATION -->\\n${pagHtml}` : base.html;
  return { ...base, html };
}
""".strip()
(OUT / "html_extract.ts").write_text(f"{html_extract_ts}\n", encoding="utf-8")
print("generated html_extract.ts")
