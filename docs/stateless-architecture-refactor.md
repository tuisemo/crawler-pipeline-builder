# 核心架构重构指南：彻底无状态化与前端扩展直连

**目标文档**：指导下一个执行 Agent 彻底重构 Sea Data Workbench 的三端通信架构。
**背景**：产品决定**废除工作台阶段的“节点测试”与“子流测试”功能**。基于此决定，后端（Backend）不再需要主动控制浏览器会话，可以彻底演进为无状态的 HTTP API（仅负责 LLM 分析与 Python Playwright 爬虫代码生成）。所有的工作台辅助交互（高亮、提取 DOM、自动分析 DOM）直接由前端向本地的 Browser Bridge 扩展发送消息完成，实现零延迟、零配置的用户体验。

---

## Phase 1: 大删除行动 (The Great Deletion)
本阶段的核心是剔除所有过时的执行引擎、WebSocket 中继和冗余代码。

### 1.1 后端清理 (Backend)
- **彻底删除**整个 `backend/runtime/` 目录（包含 `browser_session.py`, `ext_session.py`, `ext_session_mgr.py`, `async_bridge.py` 等）。
- **彻底删除** `backend/api/ext_relay.py`。
- **删除执行器**：删除 `backend/workflow/executor.py`, `executor_helpers.py`, `executor_orchestration.py`, `executor_traversal.py`, `handlers.py` 等整个工作流测试执行引擎。
- **修改 `backend/app.py`**：
  - 移除对 `ext_relay` 的 router include。
  - 移除所有关于生命周期（关闭浏览器）和 `page_session_mgr` 的引用。
- **清理 `backend/api/workflow_routes.py`**：
  - 删除 `POST /api/workflows/{id}/test-node` 路由。
  - 删除 `POST /api/workflows/{id}/test-subflow` 路由。

### 1.2 前端清理 (Frontend)
- **修改 `WorkbenchToolbar.tsx`**：
  - 移除环境切换（Cloud / Extension）UI。
  - 移除 Agent ID 的配置输入框。
  - 移除“节点测试”和“子流测试”按钮。
  - 将连接状态区改为简单的文本或 Tag：“🟢 已就绪（本地扩展加速中）” 或 “🔴 未安装扩展”。
- **修改 `App.tsx` & 全局状态**：
  - 移除所有关于 `ExecutionMode`（`executionMode` state）和 `agentId` 的 localStorage 逻辑。系统只默认使用 `extension`，不再需要 agent_id。

### 1.3 扩展清理 (Extension)
- **删除 `src/background/rpc.ts`**：废除一切 WebSocket 客户端逻辑。

---

## Phase 2: 构建纯前端扩展直连 (Frontend ↔ Extension RPC)

### 2.1 改造扩展 Background (`src/background/worker.ts`)
不再通过 WebSocket 连接后端。改为监听来自外部网页的消息。
```typescript
// 监听来自前端域名（通过 externally_connectable 授权）的消息
chrome.runtime.onMessageExternal.addListener((request, sender, sendResponse) => {
  if (request.type === 'EXTRACT_HTML') {
    // 调用 tab_queue 或注入 content script 执行 extract_html
    // 获取结果后，直接调用 sendResponse(result)
    return true; // 保持通道异步返回
  }
  // 同样处理 HIGHLIGHT_SELECTOR, TEST_SELECTOR, AUTO_DETECT
});
```
*备注：需要确保 `manifest.json` 的 `externally_connectable.matches` 中包含前端域名（如 `http://127.0.0.1:3101/*`）。*

### 2.2 改造前端 Bridge (`src/features/runtime/extensionBridge.ts`)
将原本的 `detectExtension` 拓展为一套完整的 SDK：
```typescript
export function testSelectorLocally(selector: string): Promise<any> {
    return new Promise((resolve) => {
       chrome.runtime.sendMessage(EXTENSION_ID, { type: 'TEST_SELECTOR', selector }, resolve);
    });
}
// 增加 extractHtmlLocally, autoDetectLocally, highlightLocally 等对应的方法。
```

---

## Phase 3: 辅助接口(Assist API)与大模型(LLM)重构

### 3.1 改造 `useAssistWorkbenchActions.ts` (前端)
以前前端通过 `fetch('/api/assist/test-selector')` 将任务交给后端。现在：
- `testSelector`: 直接调用 `extensionBridge.testSelectorLocally`，获取并展示结果。
- `autoDetect`: 直接调用 `extensionBridge.autoDetectLocally`，获取 `list_selector` 并展示结果。
- `extractHtml`: 直接调用 `extensionBridge.extractHtmlLocally` 拿到 `HTML Fragment`。**拿到 HTML 后**，如果是进行“智能分页分析”，则将此 HTML 发送给后端的纯计算接口。

### 3.2 改造 `backend/assist/services.py` (后端)
- **移除重度接口**：
  - 删除 `run_selector_test` 函数及其路由。
  - 删除 `extract_html_fragment` 函数及其路由。
  - 删除纯做转发的 `auto_detect` 逻辑。
- **保留并改造纯净的大模型接口**：
  - 修改 `/api/assist/analyze-pagination`：现在的入参应该**直接接收前端传过来的 `html_fragment` 和 `pruned_body_html`**，而不是接收 `session_id` 和 URL 让后端去提。
  - 后端直接拿到文本数据，调用大模型，返回分析结果（选择器、策略等）。

---

## 验证与验收标准
1. 后端启动速度极快，没有后台浏览器进程驻留，不再监听 WebSocket 端口。
2. 前端能够识别出本地扩展已安装，并在用户点击“测试选择器”时，秒级（< 50ms）在目标网页出现红色边框高亮，控制台无发往后端的网络请求。
3. 执行“智能识别分页”时，由扩展进行 `getPrunedBody`，通过 `postMessage` 交给前端，前端最终发出 POST 到后端的 `analyze-pagination`，携带几十 KB 的字符串供 LLM 分析。
4. 原本基于后端的测试用例如果大面积报错，可以直接移除那些测试环境（如 `test_workflow_executor.py` 和 `test_ext_session.py`），这是正常现象。
