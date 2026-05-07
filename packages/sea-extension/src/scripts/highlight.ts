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
