// Each exported function MUST be fully self-contained (no module-level helpers).
// chrome.scripting.executeScript({ func }) serializes only the function body via
// toString(), discarding the surrounding module scope.  Any reference to a
// sibling function (e.g. cleanHtml, getPrunedBody) would become an undefined
// variable in the target page and throw a ReferenceError at runtime.

export function bridge_extract_items(selector: string, maxItems = 3) {
  // --- self-contained helper (do NOT extract to module scope) ---
  function cleanHtml(html: string) {
    return html.replace(/\s+/g, " ").replace(/>\s+</g, "><").trim();
  }
  // --- end helper ---

  const MAX = 20 * 1024;
  try {
    const els = [...document.querySelectorAll(selector)].slice(0, maxItems);
    let html = els.map((el) => cleanHtml(el.outerHTML)).join("\n");
    const originalSize = new TextEncoder().encode(html).length;
    let truncated = false;
    if (originalSize > MAX) {
      truncated = true;
      html = html.slice(0, MAX) + "\n<!-- TRUNCATED -->";
    }
    return { html, truncated, original_size: originalSize, item_count: els.length };
  } catch (e: any) {
    return { html: "", truncated: false, original_size: 0, item_count: 0, error: e.message };
  }
}

export function bridge_extract_pagination_context(selector: string | null, maxItems = 3) {
  // --- self-contained helpers (do NOT extract to module scope) ---
  function cleanHtml(html: string) {
    return html.replace(/\s+/g, " ").replace(/>\s+</g, "><").trim();
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
          const text = node.nodeValue.replace(/\s+/g, ' ').trim();
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
      let html = els.map((el) => cleanHtml(el.outerHTML)).join("\n");
      const originalSize = new TextEncoder().encode(html).length;
      let truncated = false;
      if (originalSize > MAX_SIZE) {
        truncated = true;
        html = html.slice(0, MAX_SIZE) + "\n<!-- TRUNCATED -->";
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
    itemCount > 0 ? `<!-- ITEM_SAMPLES -->\n${itemsHtml}` : "",
    pagComponentHtml ? `<!-- PAGINATION_COMPONENT -->\n${pagComponentHtml}` : "",
    `<!-- GLOBAL_PRUNED_BODY -->\n${prunedBody}`
  ].filter(Boolean).join("\n\n");

  return {
    html: combinedHtml,
    pruned_body_html: prunedBody,
    pagination_component_html: pagComponentHtml,
    item_count: itemCount,
    method: "pruned_body_plus_context"
  };
}
