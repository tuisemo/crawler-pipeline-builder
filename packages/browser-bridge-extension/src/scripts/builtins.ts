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
    // --- XPath-compatible query (self-contained) ---
    const isXPath = /^(\/\/|\.\/\/|\(\/\/|\(\/|xpath=)/.test(selector);
    let all: Element[];
    if (isXPath) {
      const xpath = selector.replace(/^xpath=/, "");
      const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      all = [];
      for (let i = 0; i < result.snapshotLength; i++) {
        const node = result.snapshotItem(i);
        if (node instanceof Element) all.push(node);
      }
    } else {
      all = [...document.querySelectorAll(selector)];
    }
    const els = all.slice(0, max);
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
    // --- XPath-compatible query (self-contained) ---
    const isXPath = /^(\/\/|\.\/\/|\(\/\/|\(\/|xpath=)/.test(itemSelector);
    let items: Element[];
    if (isXPath) {
      const xpath = itemSelector.replace(/^xpath=/, "");
      const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      items = [];
      for (let i = 0; i < result.snapshotLength; i++) {
        const node = result.snapshotItem(i);
        if (node instanceof Element) items.push(node);
      }
    } else {
      items = [...document.querySelectorAll(itemSelector)];
    }
    const records = items.slice(0, 5).map(item => {
      const record: any = {};
      fields.forEach(f => {
        let el: Element | null = null;
        const sel = f.selector || "";
        if (/^(\/\/|\.\/\/|\(\/\/|\(\/|xpath=)/.test(sel)) {
          let xp = sel.replace(/^xpath=/, "");
          if (xp.startsWith("//")) xp = `.${xp}`;
          else if (xp.startsWith("(//")) xp = `(.${xp.slice(1)}`;
          const r = document.evaluate(xp, item, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
          el = r.singleNodeValue instanceof Element ? r.singleNodeValue : null;
        } else {
          el = item.querySelector(sel);
        }
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
    // --- XPath-compatible query (self-contained) ---
    let el: Element | null = null;
    if (/^(\/\/|\.\/\/|\(\/\/|\(\/|xpath=)/.test(selector)) {
      const xpath = selector.replace(/^xpath=/, "");
      const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
      el = result.singleNodeValue instanceof Element ? result.singleNodeValue : null;
    } else {
      el = document.querySelector(selector);
    }
    if (!el) throw new Error("Element not found: " + selector);
    (el as HTMLElement).click();
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
