# 开发者上手清单与迭代规程

## 1. 文档定位

这份文档是给接手项目的开发同学准备的“最短路径操作清单”。它不重复解释产品背景，而是把常见工作拆成可以直接执行的步骤。

建议配合以下文档使用：

- 项目能力与边界：`docs/product-guide.md`
- 工程结构与代码落点：`docs/technical-guide.md`
- UI 视觉与交互规范：`DESIGN.md`

## 2. 第一次接手项目

### 环境启动清单

1. 安装 Python 依赖：

```bash
uv sync
```

2. 启动后端：

```bash
python server.py
```

3. 启动前端：

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3101
```

4. 打开前端工作台，确认：

- 画布可见
- 左侧节点面板可添加节点
- 顶部工具栏可看到 `校验 DSL / 编排计划 / 生成骨架 / 生成爬虫脚本 / 节点测试 / 子流测试`
- 底部工作区可打开结果与 DSL 编辑器

### 最小功能验收

用默认示例流程，至少点通一次：

1. `校验 DSL`
2. `编排计划`
3. `生成骨架`
4. `子流测试`
5. `生成爬虫脚本`

如果这五步都能返回结构化结果，说明核心链路基本正常。

## 3. 提交前推荐检查

### 后端

```bash
.venv\Scripts\python.exe -m pytest tests -v
```

### 前端

```bash
cd frontend
npm run test
npm run build
```

### 文档改动

如果你的改动会影响以下任一项，记得同步文档：

- 节点类型或节点字段
- workflow API / assist API
- 脚本生成链路
- 输出模式或文件保存方式
- 工作台布局和主要交互路径

## 4. 常见需求如何进入代码

## 4.1 改一个节点的配置项

通常要改这些位置：

1. `frontend/src/features/workflow/workflowContracts.ts`
2. `frontend/src/features/workflow/workbenchDefaults.ts` 中的 palette 与默认数据
3. `frontend/src/features/workflow/components/PropertyPanel.tsx`
4. `backend/workflow/schemas.py`
5. `backend/workflow/services.py` 校验逻辑
6. `backend/workflow/compiler.py`
7. 相关测试

### 适用例子

- 给 `emit_record` 增加新输出参数
- 给 `paginate` 增加新策略字段
- 给 `extract_field` 增加新字段元数据

## 4.2 改一个节点的运行时行为

通常要改这些位置：

1. `backend/workflow/handlers.py`
2. `backend/workflow/executor.py`
3. `backend/workflow/executor_orchestration.py`
4. `tests/test_workflow_executor.py`

### 适用例子

- 让 `paginate` 真正执行翻页
- 让 `condition` 支持更多表达式
- 让 `loop` 真正驱动逐项执行

## 4.3 改脚本生成效果

通常要改这些位置：

1. `backend/workflow/compiler.py`
2. `backend/workflow/codegen.py`
3. `backend/prompts/crawler_prompt.py`
4. `backend/workflow/services.py`
5. `backend/llm/client.py`
6. `tests/test_workflow_services.py`

### 适用例子

- 调整 compile plan 输出
- 改 deterministic skeleton 结构
- 改 prompt guardrails
- 改 `lite / pro` 生成模式行为

## 4.4 改 AI 辅助链路

通常要改这些位置：

1. `backend/assist/services.py`
2. `backend/api/assist_routes.py`
3. `backend/extraction/auto_detector.py`
4. `backend/extraction/html_extractor.py`
5. `frontend/src/app/App.tsx`
6. `frontend/src/features/workflow/components/PropertyPanel.tsx`
7. `tests/test_assist_services.py`

### 适用例子

- 改字段推断返回结构
- 增加新的 assist action
- 优化分页启发式恢复

## 4.5 改工作台布局或交互

通常要改这些位置：

1. `frontend/src/app/App.tsx`
2. `frontend/src/app/components/WorkbenchToolbar.tsx`
3. `frontend/src/features/workflow/components/WorkflowCanvas.tsx`
4. `frontend/src/features/results/ResultsPanel.tsx`
5. `frontend/src/features/results/ResultDetails.tsx`
6. `frontend/src/features/workflow/components/DslEditorPanel.tsx`
7. `frontend/src/index.css`
8. `DESIGN.md`

## 5. 真实迭代 SOP

### 规程 1：新增一个节点类型

1. 先在 `docs/product-guide.md` 和 `docs/technical-guide.md` 想清楚它属于哪类能力。
2. 在 `frontend/src/features/workflow/workflowContracts.ts` 增加类型。
3. 给 `frontend/src/features/workflow/workbenchDefaults.ts` 的 palette 和默认节点数据补上入口。
4. 给 `PropertyPanel.tsx` 增加配置表单。
5. 给 `WorkflowCanvas.tsx` 增加节点视觉摘要。
6. 在 `backend/workflow/schemas.py` 加字段。
7. 在 `backend/workflow/services.py` 加校验。
8. 在 `backend/workflow/compiler.py` 决定它是否进入 plan。
9. 在 `backend/workflow/handlers.py` 决定它的执行行为。
10. 补前后端测试。
11. 更新文档。

### 规程 2：把某个“半成品能力”补成完整能力

适用对象：

- `paginate`
- `loop`
- `condition advanced`
- resume / checkpoint

步骤建议：

1. 先确认当前代码真实行为，不要直接照 archive 里的历史计划实现。
2. 先补测试，锁住现状。
3. 再改后端核心语义。
4. 再改前端说明和交互。
5. 最后更新产品文档和技术文档中的“能力边界”描述。

### 规程 3：调整脚本生成质量

1. 先看 `compile_plan` 是否已经表达出需求。
2. 再判断问题应落在 skeleton、prompt 还是 review/revision 阶段。
3. 如果是确定性逻辑，优先改 `workflow/codegen.py`。
4. 如果是模型约束问题，优先改 `backend/prompts/crawler_prompt.py`、`backend/prompts/tasks/` 与 `backend/workflow/prompting.py` 的 prompt 组装。
5. 用假 LLM 响应测试或 service 测试验证返回结构。

## 6. 现在最值得优先关注的工程现实

这些点在改需求前最好先过一遍：

1. `paginate` 运行时还不是完整翻页器。
2. `loop` 还没有成为 item 级执行调度器。
3. `condition` 的 `advanced` 目前主要是前端可选项，不代表后端已有高级表达式引擎。
4. SQLite 输出可用，但 resume 体系还没有落地。
5. browser work 当前依赖单线程 `run_blocking()` 串行执行。

## 7. 改文档的规则

当你做出下面这些改动时，应该同步更新文档：

- 新增或删除节点类型
- 修改节点字段语义
- 新增 workflow / assist API
- 改动脚本生成模式
- 改动输出模式
- 改动工作台主交互路径

优先更新顺序：

1. `docs/product-guide.md`
2. `docs/technical-guide.md`
3. `DESIGN.md`
4. `docs/README.md`（如果文档结构变化）

## 8. 合并前最后自检

提交前问自己这几个问题：

1. 这次改动是否改变了当前能力边界？
2. 前端和后端的数据契约是否仍然一致？
3. 是否补了最直接的回归测试？
4. 文档里是否还留着与代码冲突的旧说法？
5. 如果新人今天拉代码，他能不能按文档走通主流程？
