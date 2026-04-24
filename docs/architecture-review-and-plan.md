# 架构评审与优化方案

## 背景与目标

`sea-data` 当前已经从早期的页面检测/选择器工具，演进为以 DSL 工作流为核心的抓取设计与执行系统。仓库同时包含 FastAPI 后端、Playwright 浏览器运行时、LLM 生成链路，以及 React 工作台前端。从 `README.md`、`.factory/services.yaml` 与实际代码可见，项目已经把 `/api/workflows/*` 和前端工作台作为主要演进方向，但工程文档、模块边界与实现形态尚未完全收敛。

本次评审目标不是推翻现有设计，而是基于当前代码现状，识别会影响后续开发、测试稳定性和运行安全性的关键问题，并给出可执行的阶段化优化方案。文档重点关注以下目标：

- 明确当前后端、前端与工程基础设施的真实架构边界。
- 识别实现语义与设计语义不一致的位置，优先处理高风险问题。
- 给出短期可落地、中期可收敛、长期可演进的优化路径。
- 为后续拆分职责、补齐测试、统一文档提供执行顺序和索引。

## 当前架构概览

### 后端

后端入口集中在 `server.py:1`。应用生命周期仅负责启动 FastAPI 并在退出时调用 `page_session_mgr.close_all()` 与 `stop_browser()`，同时挂载 `backend/workflow_routes.py:1` 中的工作流路由。当前 `GET /` 已不再提供旧模板页面，而是直接返回 API 说明，这说明实际系统已经偏向 API 服务，而非 `AGENTS.md` 中描述的模板式页面检测器。

浏览器运行时位于 `backend/browser_session.py:1`。其核心结构为：

- 进程级单例 `_browser`
- 进程级共享 `_global_context`
- `SessionManager` 维护多个 `PageSession`
- `PageSession` 持有 `context` 与 `page`

从命名与注释看，系统希望表达“session 级隔离”，但 `SessionManager.create()` 实际通过 `get_shared_context()` 为所有 session 注入同一个 browser context，仅在 context 内创建不同 page/tab。这意味着 cookie、localStorage、权限状态与部分浏览器上下文资源仍是共享的。

工作流 HTTP 面位于 `backend/workflow_routes.py:1`，主要暴露以下接口：

- `/validate`
- `/from-legacy-config`
- `/to-prompt`
- `/generate-crawler`
- `/test-node`
- `/test-subflow`

工作流服务逻辑集中在 `backend/workflow_services.py:1`。该文件当前同时承担了：图校验、legacy config 转 DSL、prompt 组装参数抽取、LLM 驱动的脚本生成。这意味着 service 层已经混合了领域转换、接口返回形式和外部模型调用。

工作流执行位于 `backend/workflow_executor.py:1`。该模块内聚了图遍历、执行状态、日志、边界控制、节点解释执行、页面交互、抽取结果聚合、测试接口落地等多类职责，是当前后端最重的单体模块。

工作流 schema 位于 `backend/workflow_schemas.py:1`。虽然采用 Pydantic 建模，但 `NodeData` 使用 `extra="allow"` 且大量字段可选，仍以“兼容优先”的弱约束为主，尚未形成按节点类型区分的数据契约。

LLM 集成位于 `llm_client.py:1`。该文件负责 `.env` 加载、provider 判定、OpenAI/vLLM 客户端适配、系统提示词定义等，已形成相对独立的基础设施模块，但与工作流生成链路之间仍是直接耦合关系。

### 前端

前端主壳位于 `frontend/src/App.tsx:1`。该文件同时负责：

- 工作台布局与视图装配
- React Flow 画布配置
- 节点 palette 与属性面板
- DSL 文本编辑与后端校验
- 工作流动作发起（validate/prompt/test/generate）
- 结果区渲染与状态分类

这使得 `App.tsx` 已成为“页面组件 + 状态编排器 + API orchestration + 领域交互 glue code”的集合点。

`frontend/src/workflowState.ts:1` 负责 DSL/Flow 双向转换、节点类型集合、前端图结构校验、错误整理、画布状态恢复等。虽然它承担了状态相关逻辑，但实际上已混合“类型定义 + 前端 schema 校验 + 适配转换 + 交互应用逻辑”，职责边界也偏宽。

`frontend/src/App.css:1` 将整套工作台样式集中在单文件中。当前样式可用，但文件为压缩式长行表达，后续维护、定位与按区域演进成本较高。

### 工程基础设施

工程基础设施入口主要包括：

- `README.md:1`：描述产品定位、结构、API、命令与架构说明
- `AGENTS.md:1`：提供仓库级工作说明
- `.factory/library/architecture.md:1`：记录迁移期架构规划
- `.factory/services.yaml:1`：定义安装、测试、lint、服务启动命令
- `pyproject.toml:1`：Python 依赖与 pytest 配置
- `frontend/package.json:1`：前端依赖与构建/测试脚本

从这些文件可看出项目已经开始形成“Python 后端 + React 前端 + Factory 服务编排”的多栈工程结构，但文档描述和真实代码状态存在明显漂移。

## 合理性评估（优点）

1. 演进方向清晰。`server.py:1` 与 `backend/workflow_routes.py:1` 已经把 DSL 工作流接口作为主入口，说明产品核心路径已经收敛到统一的工作流模型上。
2. 后端已形成基本模块切分。浏览器运行时、路由、服务、执行器、schema、LLM 客户端分别落在不同文件中，尽管边界仍不干净，但具备进一步重构的基础。
3. 执行安全意识已经存在。`backend/workflow_executor.py:1` 中提供了 `max_steps`、`max_items`、`max_pages`、revisit fingerprint 等边界机制，说明系统已考虑有界执行与调试可观测性。
4. 前端工作台功能闭环基本成立。`frontend/src/App.tsx:1` 与 `frontend/src/workflowState.ts:1` 已支持画布编辑、DSL 编辑、后端验证、子流程测试与脚本生成，具备继续产品化的基础。
5. 工具链已初步具备双栈测试/构建入口。`pyproject.toml:1`、`.factory/services.yaml:1`、`frontend/package.json:1` 至少定义了后端测试、编译检查、前端 build/test 脚本，便于后续接入 CI。
6. LLM 能力被封装在独立模块。`llm_client.py:1` 并未散落到多个业务模块中，为后续 provider 适配和 BYOK 改造留下了清晰切入点。

## 主要问题清单（按严重度：高/中/低）

### 高严重度

1. Browser session 生命周期语义与实现不一致，存在共享 context 污染风险。
   - 证据：`backend/browser_session.py:1` 中 `SessionManager.create()` 调用 `get_shared_context()`，再创建 `PageSession(get_browser(), context=ctx)`；而 `PageSession` 注释写的是“dedicated browser context + page for a user session”。`SessionManager` 注释也强调“Each session has its own page but shares the global context”。
   - 影响：不同 session 间共享 cookie、storage、登录态与权限弹窗状态，调试结果可能串扰；当用户并发测试不同站点时，隔离语义与实现语义不匹配，容易造成难复现问题。
   - 结论：这是运行时正确性与安全边界问题，应优先治理。

2. `workflow_executor` 过重，承担过多职责，后续变更风险高。
   - 证据：`backend/workflow_executor.py:1` 同时包含 `ExecutionContext`、图遍历、节点解释、日志聚合、限流控制、浏览器页面操作、selector 测试桥接、HTTP 用例承接（`test_node`/`test_subflow`）。
   - 影响：任何新增节点类型、执行策略调整、日志格式调整、会话策略改动，都可能牵动整个模块；测试粒度也会被迫偏集成化，导致定位困难。
   - 结论：这是架构可维护性瓶颈，已经影响后续扩展速度。

3. `workflow_services` 混合了 service、HTTP 表达与 LLM 调用，模块边界不清。
   - 证据：`backend/workflow_services.py:1` 既返回 `JSONResponse`，又构造 `GenerateCrawlerResponse`，还直接调用 `get_default_client()` 和 `CrawlerPromptGenerator()`。
   - 影响：领域服务难以在 CLI、异步任务、批处理等非 HTTP 场景复用；错误表达被 FastAPI 响应模型与服务逻辑绑定，难以分层测试。
   - 结论：这是后端边界污染问题，会持续阻碍职责分离。

4. 文档与实现漂移显著，关键架构判断已失真。
   - 证据：`.factory/library/architecture.md:1` 仍写明“no React/Vite workbench exists yet in the current repo”，但 `frontend/package.json:1`、`frontend/src/App.tsx:1` 已经显示 React workbench 已存在；`AGENTS.md:1` 仍强调 `templates/index.html` 与 inspector 结构，而 `server.py:1` 已仅暴露 API 说明。
   - 影响：后续开发者容易基于过时文档做错误判断，造成重复设计、错误验证路径和迁移决策偏差。
   - 结论：这是团队协作与架构治理问题，优先级应高于一般文档修订。

### 中严重度

1. Schema 设计偏松，`NodeData` 不够强类型。
   - 证据：`backend/workflow_schemas.py:1` 中 `NodeData` 使用大量 `Optional` 字段并允许 `extra="allow"`，`fields` 仍是 `List[Dict[str, Any]]`。
   - 影响：节点类型与数据结构无法形成静态契约；很多错误只能在运行时由 executor 或 selector tester 暴露，前后端一致性依赖约定而非模型。
   - 结论：兼容性策略可以理解，但当前已经影响校验深度和 IDE/测试收益。

2. `App.tsx` 过于臃肿，页面装配与业务交互强耦合。
   - 证据：`frontend/src/App.tsx:1` 单文件承载节点定义、默认数据、结果视图、动作编排、属性面板、DSL 编辑器与工具栏。
   - 影响：任何一个区域变更都会提高整页回归风险；前端测试难以聚焦到局部组件；新人理解成本高。
   - 结论：这是前端可维护性问题，已达到应拆分阈值。

3. `workflowState.ts` 职责过多，缺少更细的状态与适配分层。
   - 证据：`frontend/src/workflowState.ts:1` 同时定义 DSL 类型、节点类型守卫、图结构校验、flow/canonical 转换、DSL apply 流程。
   - 影响：前端状态逻辑、schema 约束与 UI 交互被绑定到单文件，后续如引入 store、server schema 共享或更复杂的 graph normalization，会形成迁移阻力。
   - 结论：该模块已偏向“前端领域内核”，但尚未被显式组织。

4. 构建与依赖管理存在混用风险。
   - 证据：`README.md:1` 同时推荐 `uv sync`、`.venv\Scripts\pip install -e .`、`npm install`；`AGENTS.md:1` 仍写“no formal test suite currently in place”，与 `pyproject.toml:1`、`frontend/package.json:1`、`.factory/services.yaml:1` 中已有测试/构建脚本不一致。
   - 影响：不同开发者可能用不同依赖入口初始化环境；当 Python/Node 依赖升级时，锁文件和实际安装路径容易漂移。
   - 结论：这不是立即的功能错误，但会在 CI、交付和环境复现时放大成本。

5. LLM 配置与当前模型生态适配存在潜在错配风险。
   - 证据：`llm_client.py:1` 默认仍以 `chat.completions` 风格调用 OpenAI 兼容接口，provider 选择以 `openai/vllm/auto` 为主；而当前使用场景已经涉及更明确的 provider 语义与模型差异。
   - 影响：当模型侧切换到更严格的 provider 协议时，生成链路会在运行时暴露配置错误，而不是在配置阶段提前失败。
   - 结论：属于基础设施适配问题，应纳入中期收敛。

### 低严重度

1. `server.py` 的应用形态与项目标题、返回信息不完全一致。
   - 证据：`server.py:1` 的 `FastAPI(title="Page Inspector")` 和 `main()` 输出仍沿用旧命名，但 `GET /` 已返回 `Sea Data API - use /api/workflows/* for DSL endpoints`。
   - 影响：问题较小，但会持续释放“系统仍是 inspector”的误导信号。

2. 样式文件可维护性一般。
   - 证据：`frontend/src/App.css:1` 为大段压缩式布局样式，区域边界不明显。
   - 影响：主要是前端维护成本问题，不直接影响功能正确性。

3. 路由层仍偏薄但没有形成明确的应用服务入口。
   - 证据：`backend/workflow_routes.py:1` 目前主要转调 service/executor；若后续业务扩展，容易继续把复杂度推回 service 或 executor。
   - 影响：当前问题不突出，但需要在下一轮重构时预留应用层组织方式。

## 风险分析

1. 运行时隔离风险：共享 browser context 可能造成会话串扰、鉴权状态污染和测试结果误判，尤其在 `backend/browser_session.py:1` 当前实现下，这类问题往往不是必现错误，而是偶发污染。
2. 变更放大风险：`backend/workflow_executor.py:1` 和 `frontend/src/App.tsx:1` 都属于高集中度文件，一旦需求扩展到更多节点类型、结果面板、执行策略或调试能力，修改面会迅速扩大。
3. 契约漂移风险：`backend/workflow_schemas.py:1` 的弱类型设计会使前后端共同依赖“隐式字段约定”，当节点数据逐渐增多时，兼容性 bug 会显著增加。
4. 认知偏差风险：`.factory/library/architecture.md:1`、`AGENTS.md:1`、`README.md:1` 与实际实现不一致，意味着团队成员在调试、接手、扩展时首先获得的上下文可能就是错误的。
5. 质量门禁失衡风险：当前测试叙事以后端为主，前端虽然在 `frontend/package.json:1` 中存在 `vitest`，但仓库现状显示前端测试文件很薄弱；同时 Python 与前端依赖分别使用 `uv/pip`、`npm`，若没有统一 CI 约束，容易出现“后端能过、前端无保障”的发布风险。

## 分阶段优化方案（短期/中期/长期）

### 短期（1-2 个迭代）

1. 明确并修正 browser session 语义。
   - 方案：在 `backend/browser_session.py:1` 中二选一收敛：
     - 若追求隔离，`SessionManager.create()` 为每个 session 创建独立 context；
     - 若追求性能，保留共享 context，但必须把类型、命名、注释、接口语义全部改成“shared browsing workspace / tab session”，避免继续误导。
   - 建议：优先选择“session 独立 context”，因为当前系统以测试与调试为主，正确性优先于轻量复用。

2. 把 `workflow_services` 从 HTTP 表达中剥离。
   - 方案：把 `validate_graph`、legacy 转换、prompt config 抽取、crawler generation 分为纯领域函数与路由适配层；服务层只返回领域结果/异常，`JSONResponse` 由 `backend/workflow_routes.py:1` 处理。
   - 结果：便于单测、CLI 复用与后续异步任务扩展。

3. 为 executor 做最小拆分。
   - 方案：先从 `backend/workflow_executor.py:1` 中拆出节点执行器映射、图遍历工具、执行上下文模型三部分，不要求一步到位拆成很多文件，但要先打断单文件膨胀趋势。
   - 结果：降低后续新增节点类型时的耦合度。

4. 修正文档基线。
   - 方案：至少同步 `.factory/library/architecture.md:1` 与 `AGENTS.md:1` 的核心架构事实，消除“前端不存在”“首页仍是模板 UI”等明显失真描述。
   - 说明：本次仅评审，不修改现有文档；但这是短期必做项。

5. 建立最小前端回归面。
   - 方案：围绕 `frontend/src/App.tsx:1` 的关键行为补充 smoke test，例如 DSL 解析、按钮触发、结果区状态切换；至少覆盖当前主流程的薄弱点。

### 中期（2-4 个迭代）

1. 重构 schema 为按节点类型区分的强类型模型。
   - 方案：在 `backend/workflow_schemas.py:1` 中引入 discriminated union，例如 `OpenPageNodeData`、`SelectListNodeData`、`ExtractFieldNodeData`、`PaginateNodeData`；`fields` 使用明确模型代替 `Dict[str, Any]`。
   - 结果：提升后端校验能力，也为前后端共享 schema 或生成 TS 类型打基础。

2. 重构 executor 为“图调度 + 节点处理器”模式。
   - 方案：让 `backend/workflow_executor.py:1` 退化为 orchestration 层，节点行为拆到独立 handler；浏览器交互、抽取逻辑、分页策略以 handler 或 capability 形式组织。
   - 结果：新增节点时不再修改一个巨大 switch，单测也更容易下沉。

3. 拆分前端壳层。
   - 方案：将 `frontend/src/App.tsx:1` 拆为 `toolbar`、`canvas`、`property-panel`、`dsl-editor`、`results-panel` 等组件；把动作请求与结果归一化逻辑抽到专用 hooks 或 service 文件。
   - 结果：降低单组件复杂度，提升测试颗粒度。

4. 收敛 `workflowState.ts` 的职责。
   - 方案：把类型定义、graph normalize、DSL 校验、UI apply 逻辑拆分；若条件允许，考虑让部分类型来自后端 schema 生成结果，减少双端手工漂移。

5. 统一工程命令入口。
   - 方案：以 `.factory/services.yaml:1` 或顶层 task 入口为准，明确 Python 依赖安装只保留一种主路径，前端也固定 package manager 与锁文件策略，避免文档和实际操作分叉。

### 长期（4 个迭代以上）

1. 形成稳定的应用层分层。
   - 方向：路由层只做协议适配，应用服务层编排用例，领域层负责图/节点模型，基础设施层处理 Playwright 与 LLM provider。
   - 目标：支持未来把 workflow test、script generation、batch execution 拓展到不同入口而不互相污染。

2. 引入统一的契约与发布质量门禁。
   - 方向：后端 schema、前端类型、API contract、服务编排命令与 CI 校验统一；构建、测试、lint、基础烟测在同一流水线内固定化。

3. 规划浏览器运行时的资源治理策略。
   - 方向：按用途区分调试 session、测试 session、批量执行 session；决定是否需要 context pool、worker 隔离或远程浏览器进程管理。
   - 目标：为后续更高并发或更复杂抓取流程做准备，而不是继续依赖进程内共享对象。

## 推荐执行顺序

1. 先处理 `backend/browser_session.py:1` 的 session 语义问题，统一“隔离/共享”的真实策略。
2. 随后拆分 `backend/workflow_services.py:1`，把 HTTP 响应表达从服务逻辑移除。
3. 紧接着收缩 `backend/workflow_executor.py:1`，至少完成图调度与节点执行职责分离。
4. 在后端边界较稳定后，重构 `backend/workflow_schemas.py:1` 的强类型节点数据模型。
5. 后端契约稳定后，再拆分 `frontend/src/App.tsx:1` 与 `frontend/src/workflowState.ts:1`，避免前端在后端接口频繁变动时重复返工。
6. 并行推进文档校正与工程命令统一，优先修复 `.factory/library/architecture.md:1`、`AGENTS.md:1`、`README.md:1` 的事实漂移。
7. 最后补齐 CI 导向的测试闭环，重点提升前端 smoke test 与前后端构建一致性。

## 附录：关键文件索引

### 后端

- `server.py:1`：FastAPI 应用入口与生命周期管理。
- `backend/browser_session.py:1`：Playwright browser/context/session 生命周期与错误分类。
- `backend/workflow_routes.py:1`：工作流 API 路由定义。
- `backend/workflow_services.py:1`：图校验、legacy 转换、prompt 组装、LLM 生成脚本。
- `backend/workflow_executor.py:1`：工作流有界执行、节点测试、子流程测试。
- `backend/workflow_schemas.py:1`：请求/响应模型与 `NodeData` 定义。
- `llm_client.py:1`：LLM provider 配置、客户端封装与系统提示词。

### 前端

- `frontend/src/App.tsx:1`：React 工作台主壳，集成画布、属性编辑、动作触发与结果区。
- `frontend/src/workflowState.ts:1`：DSL/Flow 类型、转换、校验与应用逻辑。
- `frontend/src/App.css:1`：工作台整体样式与布局。

### 工程基础设施

- `README.md:1`：当前对外说明、命令入口、API 和架构描述。
- `AGENTS.md:1`：仓库开发与运行约定。
- `.factory/library/architecture.md:1`：迁移期架构规划文档，当前已部分过时。
- `.factory/services.yaml:1`：服务启动、测试、lint 等命令清单。
- `pyproject.toml:1`：Python 项目依赖与 pytest 配置。
- `frontend/package.json:1`：前端依赖、构建、测试与 lint 脚本。

## 结论

当前项目的整体方向是正确的：DSL 工作流、浏览器测试执行和 React 工作台已经形成了可持续演进的产品骨架。但实现层面最需要优先解决的不是“再加功能”，而是修正运行时语义、拆分过重模块、收紧数据契约，并同步清理已经失真的架构文档。只要先把 `browser_session`、`workflow_services`、`workflow_executor` 三个关键边界收敛，后续前端拆分、测试补齐和 CI 固化都会明显顺畅。
