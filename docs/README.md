# 文档索引

`docs/` 目录现在只保留那些能够帮助贡献者理解 **当前版本** `crawler-workflow` 的文档。

## 当前有效文档

- `documentation-audit.md`
  说明本次 `docs/` 清理的判定标准，交代哪些文件仍属有效文档，哪些文件已移入归档区。
- `product-guide.md`
  面向产品与业务理解的项目说明：工作台今天能做什么、各类节点如何工作、当前能力边界在哪里。
- `technical-guide.md`
  面向工程实现的技术说明：架构分层、模块职责、API 入口、执行语义、持久化模型、前端状态组织与迭代入口。
- `engineering-diagnosis-and-optimization-plan.md`
  面向工程治理的复盘诊断：从文件架构、功能模块、配置项、前后端通讯、测试与生产化成熟度等维度评分，并给出自上而下的优化路线。
- `optimization-implementation-plan.md`
  面向执行落地的优化细案：把诊断中的阶段性路线拆成可验收任务，并记录当前第一批改造状态。
- `prompt-autoresearch-upgrade-2026-04-29.md`
  面向模型交互质量的专项审计：按功能目标反向评估提示词，并记录如何借助 AutoResearch 方法论优化提示词质量，而不是把业务提示词改写成 AutoResearch 风格。
- `script-sandbox-technical-evaluation.md`
  面向生成脚本执行验证的技术选型说明：比较 Docker、gVisor、本地 subprocess 与 RestrictedPython，并记录当前手动沙箱执行方案。
- `developer-checklist.md`
  面向贡献者的上手清单与迭代 SOP，适合改节点、改运行时、改脚本生成、改辅助链路或改前端布局时查阅。
- `examples/workflows/eworldship_product_1772.json`
  当前仍可复用的示例 DSL，用于真实列表页采集场景。

## 专项分析文档

- `analysis/guide.md`
  当前工程与能力边界的综合阅读笔记，适合作为补充背景材料。

## 历史归档文档

- `archive/README.md`
  说明归档区的使用原则。
- `archive/*.md`
  历史架构评审、重构路线图与前瞻性设计方案。这些文件仅保留背景参考价值，**不再作为当前代码的事实依据**。

## `docs/` 之外的事实文档

- `README.md`
  项目概览、启动命令与目录结构说明。
- `DESIGN.md`
  当前前端工作台的视觉与交互规范。
- `AGENTS.md`
  仓库级协作规则与开发约束。

## 文档保留规则

只有同时满足下列至少一项的文档，才应保留在当前有效区：

- 能准确描述当前代码结构与运行行为
- 能帮助新同学今天就把项目跑起来、看懂并继续扩展
- 是会被重复使用的示例资产

出现以下情况的文档，应移入 `docs/archive/`：

- 主要是重构计划
- 主要是设计探索
- 主要是阶段性评审记录
- 描述的是尚未完整落地的未来方案
