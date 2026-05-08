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
