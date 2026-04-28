# 文档清理审计说明

## 目的

本次审计以**当前仓库结构**和**当前代码实现**为依据，对 `docs/` 下的文件重新分类。每份文件被归入以下三类之一：

- `当前有效`：直接服务于理解、运行或扩展当前代码库
- `示例资产`：可被反复使用的工作流样例或数据资产
- `历史/过程文档`：规划、整改、重构或设计过程记录，已不适合作为当前事实依据

本次整理的目标，是让有效文档保持简洁、可信、可导航，同时把仍有参考价值的历史材料妥善保存在归档区。

## 分类结果

| 原文件 | 分类 | 当前价值判断 | 处理动作 |
| --- | --- | --- | --- |
| `docs/README.md` | 当前有效 | 需要作为新的文档导航入口 | 重写 |
| `docs/architecture-review-and-plan.md` | 历史/过程文档 | 作为历史分析仍有价值，但它本质上是评审与规划文档，不应继续担当现状说明 | 移入 `docs/archive/` |
| `docs/refactor-task-roadmap.md` | 历史/过程文档 | 属于某一阶段的重构待办清单，不是面向当前代码的稳定说明文档 | 移入 `docs/archive/` |
| `docs/script-first-production-crawler-plan.md` | 历史/过程文档 | 记录了脚本优先方案的演进方向；其中部分思想已进入代码，但文件本身仍是规划稿 | 移入 `docs/archive/` |
| `docs/sqlite-output-resume-upgrade-plan.md` | 历史/过程文档 | 仓库已实现输出 sink，但文中描述的完整 checkpoint / resume 体系尚未落地 | 移入 `docs/archive/` |
| `docs/ui-ux-multilayer-redesign.md` | 历史/过程文档 | 可作为设计演进历史保留，但当前前端真实状态更应以 `DESIGN.md` 和现有代码为准 | 移入 `docs/archive/` |
| `docs/workflows/eworldship_product_1772.json` | 示例资产 | 仍是一个可复用、可讲解、可验证的 DSL 示例 | 移入 `docs/examples/workflows/` |

## 新的有效文档结构

整理后的 `docs/` 目录如下：

```text
docs/
├── README.md
├── documentation-audit.md
├── product-guide.md
├── technical-guide.md
├── developer-checklist.md
├── examples/
│   └── workflows/
│       └── eworldship_product_1772.json
└── archive/
    ├── README.md
    └── *.md
```

## 为什么选择归档，而不是直接删除

这些历史文档仍然有三类参考价值：

- 帮助理解工作台与后端为何曾被大规模重构
- 帮助理解脚本生成、输出持久化为何会成为项目重点
- 帮助回溯哪些设计思路已经讨论过，避免重复探索

之所以把它们移出有效区，是因为它们已经不足以单独指导今天的开发判断。

## 当前有效文档的编写原则

新的有效文档遵循以下原则：

1. 重要结论必须能回溯到当前代码结构或当前运行行为。
2. 产品说明必须区分“今天已经支持”与“未来可能演进”。
3. 技术说明必须采用当前模块拆分、当前 API 路径和当前节点语义。
4. 未来方案在真正落地前，默认只应留在归档区，不应混入现状说明。
