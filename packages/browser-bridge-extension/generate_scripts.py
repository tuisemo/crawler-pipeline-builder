"""
Run inside packages/browser-bridge-extension:
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


def extract(src_path: Path, var_name: str, strip_iife: bool = False) -> str:
    """Extract a triple-quoted JS string from a Python source file."""
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

auto_detect = extract(BACKEND / "extraction" / "auto_detector.py", "JS_AUTO_DETECT", strip_iife=True)
(OUT / "auto_detect.ts").write_text(
    f"export function bridge_auto_detect() {{\n{auto_detect}\n}}\n",
    encoding="utf-8",
)
print("generated auto_detect.ts")

highlight_ts = """
// Each exported function MUST be fully self-contained (no module-level helpers).
// chrome.scripting.executeScript({ func }) serializes only the function body via
// toString(), discarding the surrounding module scope.

export function bridge_highlight_selector(selector: string, clearAfterMs: number) {
  // --- self-contained cleanup helper (do NOT extract to module scope) ---
  function clearHighlight() {
    const _attr = "data-bridge-highlight";
    document.querySelectorAll(`[${_attr}]`).forEach((el) => el.removeAttribute(_attr));
    document.getElementById("bridge-highlight-style")?.remove();
  }
  // --- end helper ---

  const attr = "data-bridge-highlight";
  const styleId = "bridge-highlight-style";
  document.querySelectorAll(`[${attr}]`).forEach((el) => el.removeAttribute(attr));
  document.getElementById(styleId)?.remove();
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = `[${attr}] { outline: 3px solid #1677ff !important; outline-offset: 2px !important; box-shadow: 0 0 0 4px rgba(22, 119, 255, 0.18) !important; background-color: rgba(22, 119, 255, 0.08) !important; z-index: 9999999 !important; position: relative !important; }`;
  document.head.appendChild(style);
  try {
    const els = document.querySelectorAll(selector);
    els.forEach((el, index) => {
      el.setAttribute(attr, "true");
      if (index === 0) {
        (el as HTMLElement).scrollIntoView?.({ block: "center", inline: "nearest", behavior: "smooth" });
      }
    });
    if (clearAfterMs > 0) {
      window.setTimeout(() => clearHighlight(), clearAfterMs);
    }
    return { highlighted_count: els.length };
  } catch (e: any) {
    return { highlighted_count: 0, error: e.message };
  }
}

export function bridge_clear_highlight() {
  const attr = "data-bridge-highlight";
  document.querySelectorAll(`[${attr}]`).forEach((el) => el.removeAttribute(attr));
  document.getElementById("bridge-highlight-style")?.remove();
  return { ok: true };
}
""".strip()
(OUT / "highlight.ts").write_text(f"{highlight_ts}\n", encoding="utf-8")
print("generated highlight.ts")

html_extract_ts = """
// Each exported function MUST be fully self-contained (no module-level helpers).
// chrome.scripting.executeScript({ func }) serializes only the function body via
// toString(), discarding the surrounding module scope.  Any reference to a
// sibling function (e.g. cleanHtml, getPrunedBody) would become an undefined
// variable in the target page and throw a ReferenceError at runtime.

export function bridge_extract_items(selector: string, maxItems = 3) {
  // --- self-contained helper (do NOT extract to module scope) ---
  function cleanHtml(html: string) {
    return html.replace(/\\s+/g, " ").replace(/>\\s+</g, "><").trim();
  }
  // --- end helper ---

  const MAX = 20 * 1024;
  try {
    const els = [...document.querySelectorAll(selector)].slice(0, maxItems);
    let html = els.map((el) => cleanHtml(el.outerHTML)).join("\\n");
    const originalSize = new TextEncoder().encode(html).length;
    let truncated = false;
    if (originalSize > MAX) {
      truncated = true;
      html = html.slice(0, MAX) + "\\n<!-- TRUNCATED -->";
    }
    return { html, truncated, original_size: originalSize, item_count: els.length };
  } catch (e: any) {
    return { html: "", truncated: false, original_size: 0, item_count: 0, error: e.message };
  }
}

export function bridge_extract_pagination_context(selector: string | null, maxItems = 3) {
  // --- self-contained helpers (do NOT extract to module scope) ---
  function cleanHtml(html: string) {
    return html.replace(/\\s+/g, " ").replace(/>\\s+</g, "><").trim();
  }

  function getPrunedBody() {
    if (!document.body) return "<!-- BODY_MISSING -->";

    const bodyClone = document.body.cloneNode(true) as HTMLElement;

    const noiseSelectors = [
      "script", "style", "svg", "iframe", "noscript", "canvas", "video", "audio",
      "link", "meta", "path", "symbol"
    ];
    noiseSelectors.forEach(s => {
      bodyClone.querySelectorAll(s).forEach(el => el.remove());
    });

    const keepAttrs = ["id", "class", "href", "src", "title", "value", "name", "type", "aria-label", "aria-current"];
    const all = bodyClone.querySelectorAll("*");
    all.forEach(el => {
      for (let i = el.attributes.length - 1; i >= 0; i--) {
        const attr = el.attributes[i].name;
        if (!keepAttrs.includes(attr) && !attr.startsWith("data-")) {
          el.removeAttribute(attr);
        }
      }
      if (el.tagName === "IMG") {
        const src = el.getAttribute("src");
        if (src && src.startsWith("data:")) el.setAttribute("src", "data:...");
      }
    });

    function walkAndCollapseText(node: Node) {
      if (node.nodeType === 3) {
        if (node.nodeValue) {
          const text = node.nodeValue.replace(/\\s+/g, ' ').trim();
          if (text.length > 40) {
            node.nodeValue = text.substring(0, 40) + "...";
          } else if (text === "") {
            node.nodeValue = "";
          } else {
            node.nodeValue = text;
          }
        }
      } else {
        for (let i = 0; i < node.childNodes.length; i++) {
          walkAndCollapseText(node.childNodes[i]);
        }
      }
    }
    walkAndCollapseText(bodyClone);

    const html = cleanHtml(bodyClone.innerHTML);
    if (!html) return "<!-- PRUNED_BODY_EMPTY -->";
    return html.slice(0, 100000);
  }

  function extractItems(itemSelector: string, max = 3) {
    const MAX_SIZE = 20 * 1024;
    try {
      const els = [...document.querySelectorAll(itemSelector)].slice(0, max);
      let html = els.map((el) => cleanHtml(el.outerHTML)).join("\\n");
      const originalSize = new TextEncoder().encode(html).length;
      let truncated = false;
      if (originalSize > MAX_SIZE) {
        truncated = true;
        html = html.slice(0, MAX_SIZE) + "\\n<!-- TRUNCATED -->";
      }
      return { html, truncated, original_size: originalSize, item_count: els.length };
    } catch (e: any) {
      return { html: "", truncated: false, original_size: 0, item_count: 0, error: e.message };
    }
  }
  // --- end helpers ---

  let itemsHtml = "";
  let itemCount = 0;

  if (selector) {
    const base = extractItems(selector, maxItems);
    itemsHtml = base.html;
    itemCount = base.item_count;
  }

  const prunedBody = getPrunedBody();

  const pagSelectors = [".pagination", ".pager", "[class*=pagination]", "[class*=pager]", "nav[aria-label*=page i]", "nav"];
  let pagComponentHtml = "";
  for (const candidate of pagSelectors) {
    const el = document.querySelector(candidate);
    if (el) {
      pagComponentHtml = cleanHtml(el.outerHTML).slice(0, 5000);
      break;
    }
  }

  const combinedHtml = [
    itemCount > 0 ? `<!-- ITEM_SAMPLES -->\\n${itemsHtml}` : "",
    pagComponentHtml ? `<!-- PAGINATION_COMPONENT -->\\n${pagComponentHtml}` : "",
    `<!-- GLOBAL_PRUNED_BODY -->\\n${prunedBody}`
  ].filter(Boolean).join("\\n\\n");

  return {
    html: combinedHtml,
    pruned_body_html: prunedBody,
    pagination_component_html: pagComponentHtml,
    item_count: itemCount,
    method: "pruned_body_plus_context"
  };
}
""".strip()
(OUT / "html_extract.ts").write_text(f"{html_extract_ts}\n", encoding="utf-8")
print("generated html_extract.ts")

builtins_ts = """
export function __eval__(js: string) {
  try {
    const value = eval(js);
    return { value, ok: true };
  } catch (e: any) {
    return { value: null, ok: false, error: e.message };
  }
}

export function bridge_query_selector(selector: string, max = 5) {
  try {
    const all = document.querySelectorAll(selector);
    const els = [...all].slice(0, max);
    const elements = els.map(el => ({
      tagName: el.tagName,
      text: (el as HTMLElement).innerText?.slice(0, 100),
      className: el.className
    }));
    return { elements, count: all.length, ok: true };
  } catch (e: any) {
    return { elements: [], count: 0, ok: false, error: e.message };
  }
}

export function bridge_extract_fields(itemSelector: string, fields: any[]) {
  try {
     const items = document.querySelectorAll(itemSelector);
     const records = [...items].slice(0, 5).map(item => {
        const record: any = {};
        fields.forEach(f => {
           const el = item.querySelector(f.selector);
           record[f.name] = el ? (el as HTMLElement).innerText : "";
        });
        return record;
     });
     return { records, ok: true };
  } catch (e: any) {
     return { records: [], ok: false, error: e.message };
  }
}

export async function bridge_click_element(selector: string, waitMs = 2000) {
  try {
    const el = document.querySelector(selector) as HTMLElement;
    if (!el) throw new Error("Element not found: " + selector);
    el.click();
    await new Promise(r => setTimeout(r, waitMs));
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: e.message };
  }
}

export function bridge_scroll_to_bottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  return { ok: true };
}
""".strip()
(OUT / "builtins.ts").write_text(f"{builtins_ts}\n", encoding="utf-8")
print("generated builtins.ts")
