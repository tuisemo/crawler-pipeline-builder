# Chrome Extension Bridge — JS 脚本层与 Extension 代码

> 本文件是 `extension-bridge.md` 的配套文件，专门描述 Extension 端代码。

---

## 一、目录结构

```
packages/sea-extension/
├── manifest.json
├── package.json            # vite + typescript 构建
├── vite.config.ts
├── extract_js.py           # 构建辅助：从后端提取 JS 字符串
├── src/
│   ├── background/
│   │   ├── worker.ts       # Service Worker 入口
│   │   ├── tab_queue.ts    # 每个 Tab 的串行队列
│   │   └── rpc.ts          # WS 连接管理
│   ├── scripts/
│   │   ├── registry.ts     # JS 函数注册表
│   │   ├── auto_detect.ts  # 从后端同步的 JS（构建时生成）
│   │   ├── highlight.ts    # 从后端同步的 JS（构建时生成）
│   │   ├── html_extract.ts # 从后端同步的 JS（构建时生成）
│   │   └── builtins.ts     # 内置 JS 函数（query_all, click 等）
│   └── popup/
│       ├── popup.html
│       └── popup.ts
└── icons/icon-128.png
```

---

## 二、manifest.json

```json
{
  "manifest_version": 3,
  "name": "Sea Data Workbench Bridge",
  "version": "1.0.0",
  "description": "Local browser bridge for Sea Data Workbench",
  "permissions": ["tabs", "scripting", "storage", "activeTab"],
  "host_permissions": ["<all_urls>"],
  "background": {
    "service_worker": "dist/worker.js",
    "type": "module"
  },
  "action": {
    "default_popup": "dist/src/popup/popup.html",
    "default_icon": { "128": "icons/icon-128.png" }
  }
}
```

---

## 三、scripts/builtins.ts（内置 JS 函数）

```typescript
// 以下函数通过 executeScript 注入到目标 Tab 执行

export function sea_query_all(selector: string, maxSamples = 20) {
  try {
    const els = [...document.querySelectorAll(selector)];
    return {
      count: els.length,
      elements: els.slice(0, maxSamples).map(el => ({
        text: (el.textContent || '').trim().slice(0, 200),
        html: el.outerHTML.slice(0, 600),
        children: el.querySelectorAll('*').length,
        has_image: el.querySelectorAll('img').length > 0,
        has_link: el.querySelectorAll('a[href]').length > 0,
      }))
    };
  } catch (e: any) {
    return { error: e.message, count: 0, elements: [] };
  }
}

export function sea_extract_fields(itemSelector: string, fields: Array<{name: string; selector: string; type: string; attr?: string}>) {
  try {
    const items = [...document.querySelectorAll(itemSelector)];
    const pageUrl = location.href;
    const records = items.map((item, _idx) => {
      const record: Record<string, any> = {};
      for (const f of fields) {
        try {
          const el = item.matches(f.selector) ? item : item.querySelector(f.selector);
          if (!el) { record[f.name] = null; continue; }
          if (f.type === 'text') record[f.name] = (el as HTMLElement).innerText?.trim() ?? null;
          else if (f.type === 'html') record[f.name] = el.innerHTML;
          else if (f.type?.startsWith('attr:')) {
            const attrName = f.type.slice(5);
            let val = el.getAttribute(attrName) || null;
            if (val && f.type.includes(':abs') && pageUrl) {
              try { val = new URL(val, pageUrl).href; } catch {}
            }
            record[f.name] = val;
          } else {
            record[f.name] = null;
          }
        } catch { record[f.name] = null; }
      }
      return record;
    });
    return { records };
  } catch (e: any) {
    return { error: e.message, records: [] };
  }
}

export function sea_click_and_observe(selector: string, timeoutMs = 5000) {
  return new Promise<{clicked: boolean; domChanged: boolean; error?: string}>((resolve) => {
    try {
      const el = document.querySelector(selector) as HTMLElement | null;
      if (!el) return resolve({ clicked: false, domChanged: false, error: 'Element not found' });
      let changed = false;
      const obs = new MutationObserver(() => { changed = true; obs.disconnect(); });
      obs.observe(document.body, { childList: true, subtree: true });
      el.click();
      setTimeout(() => { obs.disconnect(); resolve({ clicked: true, domChanged: changed }); }, timeoutMs);
    } catch (e: any) {
      resolve({ clicked: false, domChanged: false, error: e.message });
    }
  });
}

export function sea_scroll_bottom() {
  window.scrollTo(0, document.body.scrollHeight);
  return { scrolled: true };
}

export function __eval__(js: string) {
  // eslint-disable-next-line no-eval
  const value = eval(js);
  return { value };
}
```

---

## 四、scripts/registry.ts

```typescript
import { sea_query_all, sea_extract_fields, sea_click_and_observe,
         sea_scroll_bottom, __eval__ } from './builtins.js';
// 以下三个文件由 extract_js.py 在构建前生成
import { sea_auto_detect } from './auto_detect.js';
import { sea_highlight, sea_clear_highlight } from './highlight.js';
import { sea_extract_html, sea_extract_html_with_pagination } from './html_extract.js';

export type ScriptFn = (...args: any[]) => any;

export const SCRIPT_REGISTRY: Record<string, ScriptFn> = {
  sea_query_all,
  sea_extract_fields,
  sea_click_and_observe,
  sea_scroll_bottom,
  sea_auto_detect,
  sea_highlight,
  sea_clear_highlight,
  sea_extract_html,
  sea_extract_html_with_pagination,
  __eval__,
};
```

---

## 五、background/tab_queue.ts

```typescript
export class TabQueue {
  private queues = new Map<number, Promise<void>>();

  async enqueue<T>(tabId: number, fn: () => Promise<T>): Promise<T> {
    let resolve!: () => void;
    const token = new Promise<void>(r => { resolve = r; });
    const prev = this.queues.get(tabId) ?? Promise.resolve();
    this.queues.set(tabId, prev.then(() => token));

    await prev;
    try {
      return await fn();
    } finally {
      resolve();
      // 清理空队列
      if (this.queues.get(tabId) === token) {
        this.queues.delete(tabId);
      }
    }
  }
}
```

---

## 六、background/rpc.ts（WS 连接）

```typescript
export interface RpcMsg { id: string; method: string; params: Record<string, any>; tabId?: number; }
export interface RpcResp { id: string; ok: boolean; tabId?: number; result?: any; error?: string; }

type PendingMap = Map<string, { resolve: (v: RpcResp) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>;

export class RpcClient {
  private ws: WebSocket | null = null;
  private pending: PendingMap = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private onMessage?: (msg: RpcMsg) => Promise<RpcResp>;

  constructor(private serverUrl: string, private agentId: string) {}

  setHandler(fn: (msg: RpcMsg) => Promise<RpcResp>) { this.onMessage = fn; }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    const url = `${this.serverUrl}/api/ext-relay/agent/${this.agentId}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log(`[Sea] Connected to ${url}`);
      this.ws!.send(JSON.stringify({ type: 'event', event: 'connected', agentId: this.agentId, version: '1.0' }));
    };

    this.ws.onmessage = async (ev) => {
      let msg: RpcMsg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (!this.onMessage) return;
      const resp = await this.onMessage(msg);
      this.ws?.send(JSON.stringify(resp));
    };

    this.ws.onclose = () => {
      console.log('[Sea] Disconnected, reconnecting in 3s...');
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.ws.onerror = (e) => console.error('[Sea] WS error', e);
  }

  sendEvent(event: object) {
    this.ws?.send(JSON.stringify({ type: 'event', ...event }));
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}
```

---

## 七、background/worker.ts（Service Worker 主入口）

```typescript
import { SCRIPT_REGISTRY } from '../scripts/registry.js';
import { TabQueue } from './tab_queue.js';
import { RpcClient } from './rpc.js';

const tabQueue = new TabQueue();
let rpc: RpcClient | null = null;

// ── 等待 Tab 加载完成 ────────────────────────────────
function waitTabLoad(tabId: number, timeoutMs = 30000): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Tab load timeout')), timeoutMs);
    function onUpdated(id: number, info: chrome.tabs.TabChangeInfo) {
      if (id === tabId && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        clearTimeout(timer);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(onUpdated);
    // 如果已经加载完成，直接返回
    chrome.tabs.get(tabId).then(tab => {
      if (tab.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        clearTimeout(timer);
        resolve();
      }
    });
  });
}

// ── 命令调度 ────────────────────────────────────────
async function dispatch(msg: any): Promise<any> {
  const { id, method, params, tabId } = msg;

  try {
    let result: any;

    if (method === 'new_tab') {
      const tab = await chrome.tabs.create({ url: params.url || 'about:blank' });
      await waitTabLoad(tab.id!);
      result = { tabId: tab.id };

    } else if (method === 'navigate') {
      await chrome.tabs.update(tabId, { url: params.url });
      await waitTabLoad(tabId);
      result = { tabId, url: params.url };

    } else if (method === 'exec_script') {
      const fn = SCRIPT_REGISTRY[params.fn];
      if (!fn) throw new Error(`Unknown script function: ${params.fn}`);
      result = await tabQueue.enqueue(tabId, () =>
        chrome.scripting.executeScript({
          target: { tabId },
          func: fn,
          args: params.args ?? [],
        }).then(r => r[0]?.result ?? {})
      );

    } else {
      throw new Error(`Unknown method: ${method}`);
    }

    return { id, ok: true, tabId, result };
  } catch (e: any) {
    return { id, ok: false, tabId, error: e.message };
  }
}

// ── Tab 生命周期监听 ────────────────────────────────
chrome.tabs.onRemoved.addListener((tabId) => {
  rpc?.sendEvent({ event: 'tab_closed', tabId });
});

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.url) rpc?.sendEvent({ event: 'tab_navigated', tabId, url: info.url });
});

// ── 初始化（从 storage 读取配置）──────────────────
chrome.storage.local.get(['serverUrl', 'agentId'], ({ serverUrl, agentId }) => {
  if (serverUrl && agentId) {
    rpc = new RpcClient(serverUrl, agentId);
    rpc.setHandler(dispatch);
    rpc.connect();
  }
});

// ── Popup 发来的配置更新 ────────────────────────────
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'CONNECT') {
    rpc?.disconnect();
    rpc = new RpcClient(msg.serverUrl, msg.agentId);
    rpc.setHandler(dispatch);
    rpc.connect();
    chrome.storage.local.set({ serverUrl: msg.serverUrl, agentId: msg.agentId });
  }
  if (msg.type === 'DISCONNECT') {
    rpc?.disconnect();
    rpc = null;
  }
});
```

---

## 八、extract_js.py（构建辅助脚本）

```python
"""
运行方式：在 packages/sea-extension/ 目录下执行
  python extract_js.py

从后端 Python 文件提取 JS 字符串，生成 TypeScript 常量文件。
后端 JS 更新后需重新运行此脚本并重新构建 Extension。
"""
import re, pathlib

ROOT = pathlib.Path(__file__).parent
BACKEND = ROOT.parents[1] / "backend"
OUT = ROOT / "src/scripts"

def extract(src_path: pathlib.Path, var_name: str) -> str:
    text = src_path.read_text(encoding="utf-8")
    m = re.search(rf'{var_name}\s*=\s*"""(.+?)"""', text, re.DOTALL)
    if not m:
        raise ValueError(f"{var_name} not found in {src_path}")
    return m.group(1).strip()

# auto_detect.py → JS_AUTO_DETECT
js = extract(BACKEND / "extraction/auto_detector.py", "JS_AUTO_DETECT")
(OUT / "auto_detect.ts").write_text(
    f"export function sea_auto_detect() {{\n{js}\n}}\n",
    encoding="utf-8"
)
print("✅ auto_detect.ts generated")

# selector_tester.py 的高亮相关常量需手动整合或提取
# 这里提供模板，根据实际代码调整
highlight_ts = '''
export function sea_highlight(selector: string, clearAfterMs: number) {
  const ATTR = "data-crawler-workflow-selector-highlight";
  const STYLE_ID = "crawler-workflow-selector-highlight-style";
  document.querySelectorAll(`[${ATTR}]`).forEach(el => el.removeAttribute(ATTR));
  const old = document.getElementById(STYLE_ID);
  if (old) old.remove();
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `[${ATTR}] { outline: 3px solid #ef4444 !important; background-color: rgba(251,191,36,0.18) !important; }`;
  document.head.appendChild(style);
  const els = document.querySelectorAll(selector);
  els.forEach((el, i) => {
    el.setAttribute(ATTR, "true");
    if (i === 0) (el as HTMLElement).scrollIntoView?.({ block: "center", behavior: "instant" });
  });
  if (clearAfterMs > 0) setTimeout(() => sea_clear_highlight(), clearAfterMs);
  return { highlighted_count: els.length };
}
export function sea_clear_highlight() {
  const ATTR = "data-crawler-workflow-selector-highlight";
  const STYLE_ID = "crawler-workflow-selector-highlight-style";
  document.querySelectorAll(`[${ATTR}]`).forEach(el => el.removeAttribute(ATTR));
  document.getElementById(STYLE_ID)?.remove();
  return { ok: true };
}
'''
(OUT / "highlight.ts").write_text(highlight_ts, encoding="utf-8")
print("✅ highlight.ts generated")

# html_extract.ts 需根据 html_extractor.py 中的 JS 逻辑手动整合
# 核心：提取 item outerHTML（前 max_items 个）并截断到 15KB
html_extract_ts = '''
export function sea_extract_html(selector: string, maxItems = 3) {
  const MAX = 15 * 1024;
  try {
    const els = [...document.querySelectorAll(selector)].slice(0, maxItems);
    let html = els.map(el => el.outerHTML).join("\\n");
    const truncated = html.length > MAX;
    if (truncated) html = html.slice(0, MAX) + "\\n<!-- TRUNCATED -->";
    return { html, truncated, item_count: els.length };
  } catch(e: any) { return { html: "", error: e.message, item_count: 0 }; }
}
export function sea_extract_html_with_pagination(selector: string, maxItems = 3) {
  const base = sea_extract_html(selector, maxItems);
  // 简化版：同时尝试查找分页控件
  const pagSels = [".pagination", ".pager", "[class*=pagination]", "nav"];
  let pagHtml = "";
  for (const s of pagSels) {
    const el = document.querySelector(s);
    if (el) { pagHtml = el.outerHTML.slice(0, 3000); break; }
  }
  return {
    ...base,
    html: base.html + (pagHtml ? "\\n<!-- PAGINATION -->\\n" + pagHtml : "")
  };
}
'''
(OUT / "html_extract.ts").write_text(html_extract_ts, encoding="utf-8")
print("✅ html_extract.ts generated")
print("\nDone. Run: cd packages/sea-extension && npm run build")
```

---

## 九、popup/popup.html

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { width: 280px; padding: 16px; font-family: sans-serif; font-size: 14px; }
    input { width: 100%; margin: 4px 0 10px; padding: 6px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }
    button { width: 100%; padding: 8px; background: #1677ff; color: white; border: none; border-radius: 4px; cursor: pointer; }
    button.disconnect { background: #ff4d4f; margin-top: 6px; }
    .status { margin-bottom: 12px; font-size: 13px; }
    .ok { color: #52c41a; } .err { color: #ff4d4f; }
  </style>
</head>
<body>
  <div class="status" id="status">⚪ 未连接</div>
  <label>服务器地址</label>
  <input id="serverUrl" placeholder="ws://your-server:8000" />
  <label>Agent ID</label>
  <input id="agentId" placeholder="my-device-id" />
  <button id="connect">连接</button>
  <button class="disconnect" id="disconnect">断开</button>
  <script src="popup.js"></script>
</body>
</html>
```

---

## 十、构建与加载步骤

```bash
# 1. 首次构建前提取 JS
cd packages/sea-extension
python extract_js.py

# 2. 安装依赖并构建
npm install
npm run build        # 输出到 dist/

# 3. Chrome 加载扩展
# 打开 chrome://extensions → 开启开发者模式 → 加载已解压的扩展程序 → 选择 packages/sea-extension/
# （dist/ 目录已通过 vite 构建到根目录，manifest.json 位于根目录）

# 4. 后端依赖更新（已有 websockets）
uv sync

# 5. 启动后端
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000

# 6. 打开 Extension Popup，填入服务器地址和 Agent ID，点击连接
# 7. 前端切换执行环境为 Extension，Agent ID 填写相同的值
```

---

## 十一、验证清单

- [ ] Extension Popup 显示"✅ 已连接"
- [ ] 后端日志出现 `[ExtRelay] Extension connected: <agent_id>`
- [ ] 前端选择 Extension 环境，open_page 节点测试能打开新 Tab
- [ ] select_list 节点测试返回正确匹配数量
- [ ] extract_field 节点测试返回字段数据
- [ ] AI 自动检测功能正常（调用 `sea_auto_detect`）
- [ ] 选择器高亮在目标 Tab 可见
- [ ] AI 分页分析功能正常（调用 `sea_extract_html_with_pagination`）
- [ ] Tab 关闭后，前端提示 session 过期
