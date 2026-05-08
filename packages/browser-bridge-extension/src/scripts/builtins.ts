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
