function cleanHtml(html: string) {
  return html.replace(/\s+/g, " ").replace(/>\s+</g, "><").trim();
}

export function sea_extract_html(selector: string, maxItems = 3) {
  const MAX = 15 * 1024;
  try {
    const els = [...document.querySelectorAll(selector)].slice(0, maxItems);
    let html = els.map((el) => cleanHtml(el.outerHTML)).join("\n");
    const originalSize = new TextEncoder().encode(html).length;
    let truncated = false;
    if (originalSize > MAX) {
      truncated = true;
      html = html.slice(0, MAX) + "\n<!-- TRUNCATED -->";
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
  const html = pagHtml ? `<!-- ITEM_SAMPLES -->\n${base.html}\n<!-- PAGINATION -->\n${pagHtml}` : base.html;
  return { ...base, html };
}
