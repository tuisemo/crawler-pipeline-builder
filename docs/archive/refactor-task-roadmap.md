# 可执行重构任务清单

## 目标与范围

本清单基于 `docs/architecture-review-and-plan.md`，用于把现有架构评审结论落地为可按阶段执行、可验收、可回滚的重构任务。目标不是一次性重写系统，而是在不改变产品主路径（DSL 工作流设计、测试执行、脚本生成）的前提下，逐步完成以下收敛：

- 明确并修正浏览器 session 生命周期与隔离语义，降低运行时串扰风险。
- 收敛后端模块边界，避免 `workflow_services`、`workflow_executor` 继续膨胀。
- 提升工作流 schema 强类型能力，减少前后端契约漂移。
- 拆分前端工作台大文件，建立组件、状态、API 调用三层结构。
- 补齐工程基础设施、文档、测试与命令约定，形成稳定的迭代基线。

范围覆盖以下文件与目录：

- 后端：`backend/browser_session.py`、`backend/workflow_routes.py`、`backend/workflow_services.py`、`backend/workflow_executor.py`、`backend/workflow_schemas.py`、`server.py`、`llm_client.py`
- 前端：`frontend/src/App.tsx`、`frontend/src/workflowState.ts`、`frontend/src/App.css`、`frontend/src/*.test.ts*`
- 基础设施：`.factory/services.yaml`、`pyproject.toml`、`frontend/package.json`、`frontend/pnpm-lock.yaml`
- 文档：`docs/architecture-review-and-plan.md`、`.factory/library/architecture.md`、`AGENTS.md`

不在本轮范围内的事项：

- 不新增新的工作流节点类型。
- 不修改现有产品定位与 API 功能集合。
- 不引入新的重型框架替代 FastAPI、Playwright、React Flow 或 Monaco。

## 任务拆分原则

1. 先收敛运行时语义，再收敛模块边界，最后再做前端拆分与文档统一。
2. 每个任务必须能独立提交、独立回归、独立回滚，避免“大重构一次合并”。
3. 优先拆出高风险交叉点：共享浏览器上下文、HTTP 与 service 混合、单体 executor、单体 App。
4. 所有拆分任务必须先定义“旧入口保持兼容多久、何时删除兼容层”。
5. 每个任务都要带验收标准，验收优先看行为与命令是否稳定，不只看代码是否拆开。
6. 测试补齐必须与模块拆分同步推进，不能等全部重构完成后再补。
7. 依赖与命令统一要服务于执行效率：同一类任务只能保留一个推荐入口。

## P0 优先级任务清单

### P0-1 browser session 生命周期与隔离语义重构

- 目标：让 `backend/browser_session.py` 的命名、实现、注释、接口语义一致，明确“session 是否独立 context”，消除跨 session 状态污染。
- 涉及文件：`backend/browser_session.py`、`server.py`、`tests/test_workflow_api.py`、`tests/test_workflow_executor.py`
- 前置条件：确认当前 `page_session_mgr` 的创建、获取、关闭入口仅由 `server.py` 与 `backend/workflow_executor.py` 使用。
- 执行步骤：
  1. 盘点 `get_shared_context()`、`PageSession`、`SessionManager.create()` 的当前行为与调用链。
  2. 选定目标语义：推荐改为“每个 session 独立 browser context，共享 browser 进程”。
  3. 重构 `PageSession.close()`，确保关闭 page 时按所有权决定是否关闭 context。
  4. 调整 `SessionManager.create()`、`cleanup()`、`close_all()`，避免 context 泄漏。
  5. 清理与“shared context/tab session”相冲突的命名、注释、错误文案。
  6. 为 session 复用、过期、关闭、并行创建补充测试。
- 验收标准：
  - 不同 session 之间不共享 cookie/localStorage/sessionStorage。
  - 关闭一个 session 不影响其他 session 的 page 与 context。
  - `tests/test_workflow_executor.py` 中至少存在一个隔离性回归用例。
  - 服务停止时不存在未关闭的 session/context 残留错误。
- 风险与回滚点：
  - 风险：独立 context 会增加内存占用与创建耗时。
  - 回滚点：若短期无法承担成本，可回滚到共享 context，但必须同步把语义、类型与注释全部改成“共享工作区/多标签页”，不能保留“独立 session”表述。

### P0-2 workflow_services 边界收敛

- 目标：让 `backend/workflow_services.py` 只保留领域服务逻辑，不直接返回 `JSONResponse`，不直接承载 HTTP 表达细节。
- 涉及文件：`backend/workflow_services.py`、`backend/workflow_routes.py`、`backend/workflow_schemas.py`
- 前置条件：梳理 `/api/workflows/validate`、`/from-legacy-config`、`/to-prompt`、`/generate-crawler` 的返回格式与错误路径。
- 执行步骤：
  1. 列出 `workflow_services` 中当前混合的职责：校验、legacy 转换、prompt 配置抽取、LLM 调用、HTTP 错误表达。
  2. 拆出纯函数/服务返回值，例如 `ValidationResult`、`PromptConfig`、`CrawlerGenerationResult`。
  3. 将 `_validation_error()`、`JSONResponse(...)` 下沉到 `backend/workflow_routes.py`。
  4. 统一 service 层异常或错误对象格式，避免有的接口抛异常、有的接口直接返回 HTTP 响应。
  5. 补充服务层单元测试，验证无 FastAPI 依赖时仍可直接调用。
- 验收标准：
  - `backend/workflow_services.py` 中不再 import `fastapi.responses.JSONResponse`。
  - 路由层负责协议转换，service 层负责业务结果。
  - 原有四个 workflow API 的成功/失败 JSON 结构保持兼容。
  - 至少补齐 validate 与 generate-crawler 的服务层测试。
- 风险与回滚点：
  - 风险：错误格式变动会影响前端结果区解析。
  - 回滚点：若前端兼容问题较多，可保留原响应字段名，但继续完成“路由层包装、service 层纯业务”的拆分。

### P0-3 workflow_executor 最小可控拆分

- 目标：把 `backend/workflow_executor.py` 从“单体执行器”拆成可演进结构，先打断职责耦合，再逐步细化。
- 涉及文件：`backend/workflow_executor.py`、`backend/workflow_schemas.py`、`backend/async_bridge.py`、`tests/test_workflow_executor.py`
- 前置条件：梳理 executor 内的职责块：执行上下文、图遍历、节点调度、节点执行、日志记录、边界控制。
- 执行步骤：
  1. 先按职责画出内部边界：`ExecutionContext`、graph traversal、node handlers、result assembler。
  2. 第一阶段至少拆出节点执行分派层，例如 `backend/workflow_executor_handlers.py` 或 `backend/workflow_executor/nodes.py`。
  3. 将 `_build_node_map()`、`_build_adjacency_map()`、`_get_prerequisite_nodes()` 等图辅助函数独立。
  4. 保留现有 `WorkflowExecutor` 对外入口，减少路由层改动面。
  5. 为 `open_page`、`select_list`、`extract_field`、`paginate` 的执行路径增加针对性测试。
- 验收标准：
  - `backend/workflow_executor.py` 不再同时承载全部图算法与全部节点执行细节。
  - `WorkflowExecutor` 入口签名保持兼容。
  - 新增节点执行测试可直接覆盖单个 handler，而不必每次走完整子流程。
  - 子流程测试结果与现有 API 返回结构一致。
- 风险与回滚点：
  - 风险：拆分后内部导入关系变复杂，短期可能出现循环依赖。
  - 回滚点：若一次拆分过大导致回归，先只拆图遍历与节点分派，不拆上下文模型与返回 schema。

### P0-4 workflow_schemas 强类型化第一阶段

- 目标：把 `backend/workflow_schemas.py` 从宽松 `NodeData` 过渡到“按节点类型区分的数据模型”，先建立约束骨架。
- 涉及文件：`backend/workflow_schemas.py`、`backend/workflow_services.py`、`backend/workflow_executor.py`、`tests/test_workflow_dsl_validation.py`
- 前置条件：整理当前支持的节点类型：`open_page`、`select_list`、`extract_field`、`paginate`、`loop`、`condition`、`emit_record`、`end`。
- 执行步骤：
  1. 为核心节点定义专属 data model，例如 `OpenPageNodeData`、`SelectListNodeData`、`ExtractFieldNodeData`、`PaginateNodeData`。
  2. 为 `fields` 定义明确模型，替代 `List[Dict[str, Any]]`。
  3. 为 `WorkflowNode` 增加按 `type` 区分的数据约束；如果一步到位风险高，可先引入显式校验函数。
  4. 让 validate 流程先消费强类型结构，再逐步下沉到 executor 与前端契约。
  5. 补充 schema 校验测试，覆盖缺字段、字段类型错误、未知字段策略。
- 验收标准：
  - 至少四类核心节点拥有独立数据模型。
  - `extract_field.fields` 不再是裸 `Dict[str, Any]`。
  - 无效节点数据在 validate 阶段即可被拒绝，而不是拖到 executor 才报错。
  - 新增测试覆盖节点级 schema 失败场景。
- 风险与回滚点：
  - 风险：强类型过早收紧会影响 legacy graph 兼容。
  - 回滚点：允许通过兼容适配函数接住旧 graph，但不能回滚为完全 `extra="allow"` 的无边界状态。

### P0-5 测试体系补齐第一阶段（后端 + 前端冒烟）

- 目标：在核心边界重构同步建立最小回归网，优先覆盖最易回归路径。
- 涉及文件：`tests/test_workflow_api.py`、`tests/test_workflow_executor.py`、`tests/test_workflow_dsl_validation.py`、`frontend/src/workflowState.test.ts`、`frontend/package.json`
- 前置条件：确认 Python 测试入口与前端 `vitest` 入口可运行，修复已删除或缺失的测试文件引用。
- 执行步骤：
  1. 修复/恢复 `frontend/src/workflowState.test.ts` 的测试基线。
  2. 为 `workflowState.ts` 增加 `validateGraphShape`、`applyDslTextChange`、`graphToFlowState` 测试。
  3. 为后端 validate/service/executor 新增最小单测与接口测试。
  4. 将前端测试命令纳入统一执行清单。
  5. 明确“提交前至少运行哪些命令”。
- 验收标准：
  - `npm run test` 可执行且至少包含 `workflowState` 相关测试。
  - `pytest tests -v` 覆盖 validate、executor、API 基本路径。
  - P0 的四个后端任务每个都有对应回归用例。
- 风险与回滚点：
  - 风险：前端测试环境依赖 Monaco/React Flow，可能需要 mock 才能稳定。
  - 回滚点：若组件级测试成本过高，P0 先锁定纯状态函数与 API service 层测试，组件交互测试延后到 P1。

## P1 优先级任务清单

### P1-1 前端 `App.tsx` 组件化拆分

- 目标：把 `frontend/src/App.tsx` 从单体页面拆成“页面壳 + 区域组件 + 结果展示组件”。
- 涉及文件：`frontend/src/App.tsx`、`frontend/src/App.css`、`frontend/src/components/*`
- 前置条件：P0 中后端 API 结构与前端结果字段保持稳定。
- 执行步骤：
  1. 先识别 `App.tsx` 中可独立的区域：toolbar、palette、canvas、property-panel、dsl-editor、results-panel。
  2. 提炼展示型组件，优先拆无副作用区域。
  3. 将 `ResultDetails`、`WorkflowCanvasNode` 等内联组件迁出。
  4. 保留 `App.tsx` 作为组装层，不再直接承载所有渲染细节。
  5. 为关键组件补充渲染/交互测试。
- 验收标准：
  - `App.tsx` 主要负责组合和状态编排，长度显著下降。
  - 新组件目录结构清晰，按功能区域命名。
  - 原有按钮操作和结果展示行为保持不变。
- 风险与回滚点：
  - 风险：拆分 props 过程中可能导致状态透传过深。
  - 回滚点：若一次性拆太多，先只拆结果区和属性面板，再拆画布与编辑器区域。

### P1-2 `workflowState.ts` 拆分

- 目标：把类型定义、图转换、DSL 校验、DSL 应用逻辑从 `frontend/src/workflowState.ts` 中拆开。
- 涉及文件：`frontend/src/workflowState.ts`、`frontend/src/workflowState/*.ts` 或 `frontend/src/workflow/*`
- 前置条件：P0-4 已提供较稳定的后端 schema 方向。
- 执行步骤：
  1. 拆出纯类型定义，如 `types.ts`。
  2. 拆出 graph normalize / flow adapter，如 `graphAdapters.ts`。
  3. 拆出 DSL 校验与错误整理，如 `dslValidation.ts`。
  4. 保留对外稳定入口文件，避免大量引用点同时改动。
  5. 为每个拆分模块补独立测试。
- 验收标准：
  - `workflowState.ts` 不再同时承载类型、校验、转换、应用流程。
  - `validateGraphShape`、`toCanonicalGraph`、`applyDslTextChange` 分别位于职责明确的模块。
  - 现有前端调用方仅需少量迁移。
- 风险与回滚点：
  - 风险：前后端类型命名不统一会放大理解成本。
  - 回滚点：若目录拆分影响过大，可先逻辑拆文件、后统一命名。

### P1-3 workflow API service/hooks 分层

- 目标：把 `App.tsx` 中直接 `fetch('/api/workflows/*')` 的逻辑抽离为 service 与 hooks 两层。
- 涉及文件：`frontend/src/App.tsx`、`frontend/src/services/workflowApi.ts`、`frontend/src/hooks/useWorkflowActions.ts`
- 前置条件：P1-1 已完成组件拆分，便于把请求逻辑统一沉到 hooks。
- 执行步骤：
  1. 提炼 API client：validate、to-prompt、test-node、test-subflow、generate-crawler。
  2. 统一请求错误、session_expired、partial、runtime-error 的归一化处理。
  3. 用 `useWorkflowActions` 管理 running state、结果态、错误态。
  4. 从 UI 组件中移除直接 `fetch` 与重复 payload 拼装逻辑。
  5. 为 service/hook 增加 mock 测试。
- 验收标准：
  - UI 组件不再直接拼接 workflow API URL 与请求体。
  - 结果状态转换逻辑集中在 hooks/service 层。
  - 新增测试覆盖成功、校验失败、session 失效三类分支。
- 风险与回滚点：
  - 风险：hooks 过度集中会形成新的“大 hook”。
  - 回滚点：若 action 过多，可拆成 `useWorkflowValidation`、`useWorkflowExecution`、`useCrawlerGeneration`。

### P1-4 文档与 `.factory` 基础设施校准

- 目标：修正文档、服务编排、真实架构之间的漂移，保证新人按文档即可启动与验证。
- 涉及文件：`.factory/library/architecture.md`、`AGENTS.md`、`.factory/services.yaml`、`docs/architecture-review-and-plan.md`
- 前置条件：P0 关键边界已确定，避免文档刚写完又因语义变化失效。
- 执行步骤：
  1. 逐项核对架构文档、服务命令、当前仓库结构是否一致。
  2. 删除“前端尚不存在”“首页是模板 inspector”等过时叙述。
  3. 校准 `.factory/services.yaml` 中 lint/test/install 命令与真实文件列表。
  4. 将重构后的模块边界、推荐命令、验证方式同步到内部文档。
- 验收标准：
  - `.factory/library/architecture.md` 与真实架构一致。
  - `.factory/services.yaml` 中的 lint/test 命令不再引用已删除或不再主用的文件。
  - 内部文档能指导完成一次完整开发环境启动与测试。
- 风险与回滚点：
  - 风险：文档校准晚于代码变化，容易再次过期。
  - 回滚点：文档提交必须绑定对应代码任务，同一迭代内完成，不单独长期搁置。

### P1-5 依赖/命令统一第一阶段（uv、npm/pnpm、services.yaml）

- 目标：统一 Python 与前端依赖安装、测试、构建入口，避免多套命令长期并存。
- 涉及文件：`pyproject.toml`、`uv.lock`、`frontend/package.json`、`frontend/pnpm-lock.yaml`、`.factory/services.yaml`
- 前置条件：确认团队主用 Node 包管理器与 Python 安装路径。
- 执行步骤：
  1. 选定 Python 主入口为 `uv sync` 或 `.venv\Scripts\python -m pip install -e .`，并明确一个为推荐标准。
  2. 选定前端包管理器为 `npm` 或 `pnpm`，避免脚本与锁文件分裂。
  3. 更新 `.factory/services.yaml`，让 install/test/build 命令与选定工具一致。
  4. 核对锁文件是否保留、是否需要补充 install 校验。
  5. 将命令统一结论同步到内部执行文档。
- 验收标准：
  - Python 依赖安装只有一个主推荐命令。
  - 前端只保留一个主包管理器和与之对应的锁文件策略。
  - `.factory/services.yaml` 可以直接作为开发/测试自动化入口。
- 风险与回滚点：
  - 风险：团队成员本地已有不同工具链缓存，切换时会出现环境波动。
  - 回滚点：短期可保留兼容命令说明，但 CI 与 `.factory/services.yaml` 必须先统一。

## P2 优先级任务清单

### P2-1 workflow_executor 深度拆分与能力边界固化

- 目标：在 P0 最小拆分基础上，进一步形成“调度器 + handler + 浏览器能力适配层”的稳定结构。
- 涉及文件：`backend/workflow_executor.py`、`backend/workflow_executor/*`、`extraction/selector_tester.py`
- 前置条件：P0-3 已完成第一阶段拆分，执行器行为稳定。
- 执行步骤：
  1. 继续把节点 handler 按能力分组，如页面导航、列表选择、字段抽取、分页推进。
  2. 为执行日志、状态快照、结果聚合建立独立模块。
  3. 抽离与 Playwright/selector tester 直接耦合的能力接口。
  4. 为后续新增节点类型预留扩展注册机制。
- 验收标准：
  - 新增一个节点 handler 时，不需要修改 executor 主循环的大段条件分支。
  - handler 可单测，调度器可单测，端到端子流程可集成测。
- 风险与回滚点：
  - 风险：过度抽象会让当前简单节点执行路径变难理解。
  - 回滚点：优先抽公共能力，不为暂时不存在的节点提前设计过深抽象。

### P2-2 workflow_schemas 与前端类型共享策略

- 目标：减少 `backend/workflow_schemas.py` 与 `frontend/src/workflowState.ts` 的手工重复定义。
- 涉及文件：`backend/workflow_schemas.py`、`frontend/src/workflowState.ts`、`frontend/src/workflow/types.ts`
- 前置条件：P0-4 与 P1-2 已稳定。
- 执行步骤：
  1. 评估是通过手写共享契约文件，还是通过 schema 导出生成 TS 类型。
  2. 明确哪些字段以后端为源，哪些字段为前端画布专有字段（如 `label`、`position`）。
  3. 建立契约变更检查，避免后端 schema 变化未同步到前端。
- 验收标准：
  - 节点类型、字段名、字段结构不再双端各维护一套独立事实来源。
  - 画布专有字段与工作流契约字段边界清晰。
- 风险与回滚点：
  - 风险：自动生成类型链路增加构建复杂度。
  - 回滚点：如生成链路成本过高，可先维护单一手写契约源，再做生成。

### P2-3 测试体系补齐第二阶段（前端组件/端到端）

- 目标：把测试从“状态函数级”扩展到“组件交互级”和必要的端到端烟测。
- 涉及文件：`frontend/src/components/*.test.tsx`、`frontend/src/hooks/*.test.ts`、`.factory/services.yaml`
- 前置条件：P1 的组件化与 hooks 分层已完成。
- 执行步骤：
  1. 为 toolbar、results-panel、property-panel 增加组件测试。
  2. 为 workflow actions hooks 增加 API mock 测试。
  3. 视成本引入最小端到端烟测，覆盖“validate -> prompt/test -> result”主链路。
  4. 将前端测试分层纳入统一命令。
- 验收标准：
  - 前端至少具备状态函数测试、hooks 测试、组件测试三层覆盖。
  - 核心工作台主流程有自动化冒烟验证。
- 风险与回滚点：
  - 风险：端到端测试对浏览器环境依赖重，稳定性要求高。
  - 回滚点：若 E2E 成本不合适，先以 hooks + 组件测试替代。

### P2-4 文档与命令治理常态化

- 目标：把文档同步、命令维护、`.factory` 配置校准从一次性清理变成持续动作。
- 涉及文件：`.factory/services.yaml`、`AGENTS.md`、`.factory/library/architecture.md`、`docs/*.md`
- 前置条件：P1-4、P1-5 已完成。
- 执行步骤：
  1. 规定所有模块边界调整必须同步更新对应内部文档。
  2. 在测试或 CI 中增加对关键命令可执行性的验证。
  3. 约定 `.factory/services.yaml` 为自动化入口真源，文档只引用它，不重复维护多套命令。
- 验收标准：
  - 关键命令不再出现“文档写法”和“自动化写法”长期不一致。
  - 架构文档与仓库实际结构的漂移在一个迭代内可被发现并修复。
- 风险与回滚点：
  - 风险：若没有固定责任人，文档仍会再次失真。
  - 回滚点：至少先把每个迭代的收尾 checklist 固定下来，避免完全依赖人工记忆。

## 任务依赖关系

- `P0-1 browser session 生命周期与隔离语义重构` 是后端运行时基础，先于 executor 深拆。
- `P0-2 workflow_services 边界收敛` 与 `P0-4 workflow_schemas 强类型化第一阶段` 相互关联，但建议先做 P0-2，再做 P0-4，避免强类型设计被 HTTP 细节牵制。
- `P0-3 workflow_executor 最小可控拆分` 依赖 P0-1 的 session 语义稳定，否则执行器拆分后还要重改会话模型。
- `P0-5 测试体系补齐第一阶段` 要与 P0-1 ~ P0-4 并行推进，但验收上依赖这些任务落地后的真实边界。
- `P1-1 App.tsx 组件化拆分` 依赖 P0 阶段后端 API 结果结构基本稳定。
- `P1-2 workflowState.ts 拆分` 与 `P1-3 workflow API service/hooks 分层` 建议串行推进，先拆状态，再拆 API 交互。
- `P1-4 文档与 .factory 基础设施校准` 依赖 P0/P1 的实际结构落定，否则文档容易重复返工。
- `P1-5 依赖/命令统一` 可与 P1-4 并行，但应在测试命令稳定后再最终收口。
- `P2-1`、`P2-2`、`P2-3` 建立在 P0/P1 已形成清晰边界基础上。

## 推荐迭代顺序

### 第 1 周：先修运行时语义与最低测试网

优先执行：P0-1、P0-5（后端隔离相关用例）

- 先做什么：先改 `backend/browser_session.py`，同时补 session 隔离与关闭行为测试。
- 后做什么：再跑 executor/API 回归，确认执行链路不被 session 调整破坏。
- 为什么：session 语义错误属于高风险基础问题，不先修正，后续 executor 与服务边界拆分都会建立在错误抽象上。

### 第 2 周：收敛 service 边界与 executor 最小拆分

优先执行：P0-2、P0-3、P0-5（服务层与执行器测试）

- 先做什么：先把 `workflow_services` 里的 HTTP 响应剥出去。
- 后做什么：随后拆 `workflow_executor` 的图遍历与节点执行分派。
- 为什么：先去掉服务层中的协议噪音，才能更清楚地定义 executor 的输入/输出边界，减少拆分时的交叉耦合。

### 第 3 周：收紧 schema 契约，稳定后端边界

优先执行：P0-4、补齐 P0-5

- 先做什么：为核心节点建立强类型数据模型。
- 后做什么：同步调整 validate、service、executor 消费方式，并完成 schema 回归测试。
- 为什么：后端边界在这一阶段收口后，前端才能基于稳定契约拆状态与接口层，避免重复返工。

### 第 4 周：拆前端 App 与 workflowState

优先执行：P1-1、P1-2、P1-3

- 先做什么：先拆 `App.tsx` 中无副作用区域与结果展示区。
- 后做什么：再拆 `workflowState.ts`，最后提炼 workflow API service/hooks。
- 为什么：先把 UI 结构拆散，再拆状态与请求逻辑，能降低一次改动面的复杂度，也更利于测试落位。

### 第 5 周：校准文档、命令与自动化入口

优先执行：P1-4、P1-5

- 先做什么：对齐 `.factory/services.yaml`、内部架构文档、仓库真实结构。
- 后做什么：统一 uv / npm 或 pnpm 的推荐命令与锁文件策略。
- 为什么：这一阶段代码边界已基本稳定，文档和命令才能一次收口，避免边改边失效。

### 第 6 周及以后：深拆、共享契约与前端测试扩展

优先执行：P2-1、P2-2、P2-3、P2-4

- 先做什么：先深拆 executor 与共享契约，再扩展前端组件/端到端测试。
- 后做什么：将文档与命令治理纳入持续流程。
- 为什么：这些任务属于放大长期收益的工程化动作，应建立在前几周已经稳定的模块边界之上。

## 顺序说明：先做什么、后做什么、为什么

建议严格遵循以下主线：

1. 先修 `backend/browser_session.py`，因为它决定执行期隔离语义，是所有后端测试与执行行为的基础。
2. 再拆 `backend/workflow_services.py`，因为必须先分清“业务结果”和“HTTP 响应”才能让后续模块边界明确。
3. 然后拆 `backend/workflow_executor.py`，因为执行器是当前后端复杂度最高的聚合点，越晚拆，后续新需求越难接入。
4. 接着收紧 `backend/workflow_schemas.py`，因为只有在 service/executor 边界稳定后，强类型模型才不会频繁返工。
5. 后端契约稳定后，再拆 `frontend/src/App.tsx` 与 `frontend/src/workflowState.ts`，因为前端分层会依赖后端接口与 schema 形态。
6. 最后统一 `.factory/services.yaml`、依赖安装入口和内部文档，因为这些基础设施应以稳定架构为准绳，而不是跟着中途过渡方案波动。

这个顺序的核心原因是：先解基础运行时问题，再解模块边界问题，再解前端结构问题，最后收口工程治理。这样每一步都能建立在前一步已经稳定的事实之上，避免反复推翻。
