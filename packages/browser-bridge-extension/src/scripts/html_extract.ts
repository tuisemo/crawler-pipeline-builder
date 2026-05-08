// Each exported function MUST be fully self-contained (no module-level helpers).
// chrome.scripting.executeScript({ func }) serializes only the function body via
// toString(), discarding the surrounding module scope.  Any reference to a
// sibling function (e.g. cleanHtml, getPrunedBody) would become an undefined
// variable in the target page and throw a ReferenceError at runtime.

export function bridge_extract_items(selector: string, maxItems = 3) {
  // --- self-contained helpers (do NOT extract to module scope) ---
  function cleanHtml(html: string) {
    return html.replace(/\s+/g, " ").replace(/>\s+</g, "><").trim();
  }
  function stripBridgeMarkers(html: string) {
    return html.replace(/\s+data-sea-auto="[^"]*"/g, "").replace(/\s+data-bridge-highlight="[^"]*"/g, "");
  }
  function queryAll(sel: string): Element[] {
    if (/^(\/\/|\.\/\/|\(\/\/|\(\/|xpath=)/.test(sel)) {
      const xp = sel.replace(/^xpath=/, "");
      const r = document.evaluate(xp, document, null, 7, null);
      const out: Element[] = [];
      for (let i = 0; i < r.snapshotLength; i++) {
        const n = r.snapshotItem(i);
        if (n instanceof Element) out.push(n);
      }
      return out;
    }
    return [...document.querySelectorAll(sel)];
  }
  // --- end helpers ---

  const MAX = 20 * 1024;
  try {
    const els = queryAll(selector).slice(0, maxItems);
    let html = stripBridgeMarkers(els.map((el) => cleanHtml(el.outerHTML)).join("\n"));
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

export function bridge_extract_pagination_context() {
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

    const markerAttrs = ["data-sea-auto", "data-bridge-highlight"];
    const keepAttrs = ["id", "class", "href", "src", "title", "value", "name", "type", "aria-label", "aria-current"];
    const all = bodyClone.querySelectorAll("*");
    all.forEach(el => {
      for (let i = el.attributes.length - 1; i >= 0; i--) {
        const attr = el.attributes[i].name;
        if (markerAttrs.includes(attr) || (!keepAttrs.includes(attr) && !attr.startsWith("data-"))) {
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

  function stripBridgeMarkers(html: string) {
    return html.replace(/\s+data-sea-auto="[^"]*"/g, "").replace(/\s+data-bridge-highlight="[^"]*"/g, "");
  }

  // --- end helpers ---

  const prunedBody = getPrunedBody();

  const pagSelectors = [".pagination", ".pager", "[class*=pagination]", "[class*=pager]", "nav[aria-label*=page i]", "nav"];
  let pagComponentHtml = "";
  for (const candidate of pagSelectors) {
    const el = document.querySelector(candidate);
    if (el) {
      pagComponentHtml = stripBridgeMarkers(cleanHtml(el.outerHTML)).slice(0, 5000);
      break;
    }
  }

  const combinedHtml = [
    pagComponentHtml ? `<!-- PAGINATION_COMPONENT -->\n${pagComponentHtml}` : "",
    `<!-- GLOBAL_PRUNED_BODY -->\n${prunedBody}`
  ].filter(Boolean).join("\n\n");

  return {
    html: combinedHtml,
    pruned_body_html: prunedBody,
    pagination_component_html: pagComponentHtml,
    item_count: 0,
    method: "pruned_body_plus_context"
  };
}
